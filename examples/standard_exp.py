#! /usr/bin/env python

import os
import platform
import shutil
from subprocess import call
import sys

from lab.environments import LocalEnvironment, GkiGridEnvironment
from lab.steps import Step
from lab import tools

from downward.experiment import DownwardExperiment
from downward.reports.absolute import AbsoluteReport


NODE = platform.node()
REMOTE = NODE.startswith('gkigrid') or NODE == 'habakuk'
ATTRIBUTES = ['coverage', 'cost', 'total_time']

REMOTE_EXPS = '/home/seipp/experiments' #'/users/seipp/experiments/'
LOCAL_EXPS = '/home/jendrik/lab/experiments'

REMOTE_REPO = '/home/seipp/projects/downward'
LOCAL_REPO = '/home/jendrik/projects/Downward/downward'

REMOTE_PYTHON = '/home/seipp/bin/Python/Python-2.7.3/installed/usr/local/bin/python'
LOCAL_PYTHON = 'python2.7'

if REMOTE:
    EXPS = REMOTE_EXPS
    REPO = REMOTE_REPO
    PYTHON = REMOTE_PYTHON
else:
    EXPS = LOCAL_EXPS
    REPO = LOCAL_REPO
    PYTHON = LOCAL_PYTHON


class StandardDownwardExperiment(DownwardExperiment):
    def __init__(self, path=None, repo=None, environment=None,
                 combinations=None, limits=None, attributes=None, priority=0,
                 queue='opteron_core.q'):
        if path is None:
            path = os.path.splitext(os.path.basename(sys.argv[0]))[0]
        assert not os.path.isabs(path), path
        expname = path

        remote_exppath = os.path.join(REMOTE_EXPS, path)
        local_exppath = os.path.join(LOCAL_EXPS, path)

        if REMOTE:
            exppath = remote_exppath
            repo = repo or REMOTE_REPO
            environment = environment or GkiGridEnvironment(priority=priority,
                                                            queue=queue)
        else:
            exppath = local_exppath
            repo = repo or LOCAL_REPO
            environment = environment or LocalEnvironment()

        DownwardExperiment.__init__(self, path=exppath, environment=environment,
                                    repo=repo, combinations=combinations,
                                    limits=limits)

        if attributes is None:
            attributes = ATTRIBUTES

        # Add report steps
        abs_domain_report_file = os.path.join(self.eval_dir, '%s-abs-d.html' % expname)
        abs_problem_report_file = os.path.join(self.eval_dir, '%s-abs-p.html' % expname)
        self.add_step(Step('report-abs-d', AbsoluteReport('domain', attributes=attributes),
                                                          self.eval_dir, abs_domain_report_file))
        self.add_step(Step('report-abs-p', AbsoluteReport('problem', attributes=attributes),
                                                          self.eval_dir, abs_problem_report_file))

        def get_public_location(path):
            name = os.path.basename(path)
            user_home = os.path.expanduser('~')
            user_name = os.path.basename(user_home)
            local = os.path.join(user_home, '.public_html/', name)
            public = 'http://www.informatik.uni-freiburg.de/~%s/%s' % (user_name, name)
            return local, public

        dom_local, dom_pub = get_public_location(abs_domain_report_file)
        prob_local, prob_pub = get_public_location(abs_problem_report_file)

        def publish():
            for src, local, public in [(abs_domain_report_file, dom_local, dom_pub),
                                       (abs_problem_report_file, prob_local, prob_pub)]:
                shutil.copy2(src, local)
                print 'Copied report to file://%s' % local
                print '-> %s' % public

        # Copy the results
        self.add_step(Step('publish', publish))

        # Compress the experiment directory
        self.add_step(Step.zip_exp_dir(self))

        if REMOTE:
            self.add_step(Step.remove_exp_dir(self))

        if not REMOTE:
            # Unzip the experiment directory
            self.add_step(Step.unzip_exp_dir(self))

            # Remove eval dir for a clean scp copy.
            self.add_step(Step('remove-eval-dir', shutil.rmtree, self.eval_dir))

            # Copy the results to local directory
            self.add_step(Step('scp-eval-dir', call, ['scp', '-r',
                'downward@habakuk:%s-eval' % remote_exppath, '%s-eval' % local_exppath]))

            # Copy the zipped experiment directory to local directory
            self.add_step(Step('scp-exp-dir', call, ['scp', '-r',
                'downward@habakuk:%s.tar.gz' % remote_exppath, '%s.tar.gz' % local_exppath]))

        self.add_step(Step('sendmail', tools.sendmail, 'seipp@informatik.uni-freiburg.de',
                           'seipp@informatik.uni-freiburg.de', 'Exp finished: %s' % self.name,
                           'Path: %s\n%s\n%s' % (self.path, dom_pub, prob_pub)))

    def add_config_module(self, path):
        """*path* must be a path to a python module containing only Fast
        Downward configurations in the form

        my_config = ["--search", "astar(lmcut())"]
        """
        module = tools.import_python_file(path)
        configs = [(c, getattr(module, c)) for c in dir(module)
                   if not c.startswith('__')]
        for nick, config in configs:
            self.add_config(nick, config)

    def add_ipc_config(self, ipc_config_name):
        """Example: ::

            exp.add_ipc_config('seq-sat-lama-2011')
        """
        self.add_config(ipc_config_name, ['ipc', ipc_config_name, '--plan-file', 'sas_plan'])




def get_exp(suite, configs, combinations=None, limits=None, attributes=None):
    exp = StandardDownwardExperiment(combinations=combinations, limits=limits,
                                     attributes=attributes)

    exp.add_suite(suite)
    for nick, config in configs:
        exp.add_config(nick, config)
    return exp
