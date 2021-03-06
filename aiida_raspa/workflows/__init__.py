from __future__ import print_function

from aiida.common.extendeddicts import AttributeDict
from aiida.work.run import submit
from aiida.work.workchain import WorkChain, Outputs
from aiida.orm.code import Code
from aiida.orm.data.cif import CifData
from aiida.orm.data.folder import FolderData
from aiida.orm.data.parameter import ParameterData
from aiida.orm.utils import CalculationFactory
from aiida.work.workchain import ToContext, if_, while_

RaspaCalculation = CalculationFactory('raspa')

default_options = {
        "resources": {
            "num_machines": 1,
            "num_mpiprocs_per_machine": 1,
            },
        "max_wallclock_seconds": 1 * 60 * 60,
        }

class RaspaConvergeWorkChain(WorkChain):
    """A base workchain to get converged RASPA calculations"""
    @classmethod
    def define(cls, spec):
        super(RaspaConvergeWorkChain, cls).define(spec)
        
        spec.input('code', valid_type=Code)
        spec.input('structure', valid_type=CifData)
        spec.input("parameters", valid_type=ParameterData,
                default=ParameterData(dict={}))
        spec.input("options", valid_type=ParameterData,
                default=ParameterData(dict=default_options))
        spec.input('retrieved_parent_folder', valid_type=FolderData,
                default=None, required=False)
        
        spec.outline(
            cls.setup,
            while_(cls.should_run_calculation)(
                cls.prepare_calculation,
                cls.run_calculation,
                cls.inspect_calculation,
            ),
            cls.return_results,
        )
        spec.output('retrieved_parent_folder', valid_type=FolderData)

    def setup(self):
        """Perform initial setup"""
        self.ctx.done = False
        self.ctx.nruns = 0
        self.ctx.structure = self.inputs.structure
        self.ctx.parameters = self.inputs.parameters.get_dict()
        try:
            self.ctx.restart_calc = self.inputs.retrieved_parent_folder
        except:
            self.ctx.restart_calc = None
        self.ctx.options = self.inputs.options.get_dict()

    def should_run_calculation(self):
        return not self.ctx.done
    
    def prepare_calculation(self):
        """Prepare all the neccessary input links to run the calculation"""
        self.ctx.inputs = AttributeDict({
            'code'        : self.inputs.code,
            'structure'   : self.ctx.structure,
            '_options'    : self.ctx.options,
            })

        if self.ctx.restart_calc is not None:
            self.ctx.inputs['retrieved_parent_folder'] = self.ctx.restart_calc

        # use the new parameters
        p = ParameterData(dict=self.ctx.parameters)
        p.store()
        self.ctx.inputs['parameters'] = p

    def run_calculation(self): 
        """Run raspa calculation."""

        # Create the calculation process and launch it
        process = RaspaCalculation.process()
        future  = submit(process, **self.ctx.inputs)
        self.report("pk: {} | Running calculation with"
                " RASPA".format(future.pid))
        self.ctx.nruns += 1
        return ToContext(calculation=Outputs(future))

    def inspect_calculation(self):
        """
        Analyse the results of CP2K calculation and decide weather there is a
        need to restart it. If yes, then decide exactly how to restart the
        calculation.
        """
        converged_mc = True
        self.ctx.restart_calc = self.ctx.calculation['retrieved']
        if converged_mc:
            self.report("Calculation converged, terminating the workflow")
            self.ctx.done = True

    def return_results(self):
        self.out('retrieved_parent_folder', self.ctx.restart_calc)
