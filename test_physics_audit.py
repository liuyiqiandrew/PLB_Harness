"""Run native audit handoffs offline with Harbor installed and benchmark Python dependencies on PATH."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from harbor.models.task.task import Task

from benchmark import ROOT
from physics_audit import prepare_audit


SOURCE = ROOT / 'tasks/finite-ion-cloud'


def files(directory):
    return {p.relative_to(directory): p.read_bytes() for p in directory.rglob('*') if p.is_file()}


def run_script(script, container):
    # Translate the container paths to temporary directories.
    command = script.read_text()
    for prefix in ('/logs', '/app', '/tests'):
        command = command.replace(prefix, str(container / prefix[1:]))
    return subprocess.run(['/bin/bash', '-ec', command], cwd=container / 'app',
                          capture_output=True, text=True, timeout=60, check=True)


class PhysicsAuditTest(unittest.TestCase):
    def check_handoffs(self, root, access, review):
        staged = root / 'staged'
        shutil.copytree(SOURCE, staged)
        prepare_audit(staged, f'{access}-{review}')
        task = Task(staged)
        self.assertEqual([s.name for s in task.config.steps], ['derive', 'design', 'review', 'repair'])
        self.assertEqual(task.config.multi_step_reward_strategy.value, 'final')
        self.assertEqual(sum(s.agent.timeout_sec for s in task.config.steps), 600)
        self.assertFalse((staged / 'tests').exists())  # Harbor uploads shared tests on every step.
        self.assertEqual(files(staged / 'steps/repair/tests'), files(SOURCE / 'tests'))

        env = root / 'container'
        app = env / 'app'
        shutil.copytree(staged / 'environment', app)
        verifier = env / 'logs/verifier'
        verifier.mkdir(parents=True)
        audit = app / 'audit'
        model = app / 'model.py'
        original = (SOURCE / 'environment/model.py').read_bytes()
        instruction = (SOURCE / 'instruction.md').read_text().strip()
        hint = (SOURCE / 'hint.md').read_text().strip()
        for step in task.config.steps:
            name = step.name
            prompt = task.step_instruction(name)
            if name == 'repair':
                self.assertIn(instruction, prompt)
            else:
                self.assertIn('/app/task.md', prompt)
                self.assertEqual((staged / 'steps/derive/workdir/task.md').read_text().strip(), instruction)
            self.assertNotIn(hint, prompt)
            workdir = staged / 'steps' / name / 'workdir'
            if workdir.exists():
                shutil.copytree(workdir, app, dirs_exist_ok=True)
                if name == 'derive' and sys.platform != 'linux':
                    # Run pytest on the host. The Linux subprocess guard is
                    # exercised separately in test_audit_watchdog.py.
                    (app / '.audit-runtime/audit_watchdog.py').write_text(
                        'import os, subprocess, sys\nfrom pathlib import Path\n'
                        'proc = subprocess.run(sys.argv[2:], timeout=45)\n'
                        '(Path(os.environ["AUDIT_WATCHDOG_LOGS"])/"phase-closed.txt").touch()\n'
                        'sys.exit(proc.returncode)\n'
                    )
                if (workdir / 'setup.sh').exists():
                    run_script(workdir / 'setup.sh', env)
            if name in ('derive', 'design') and access == 'delayed':
                self.assertFalse(model.is_file())
                self.assertNotIn(original, files(app).values())
            else:
                self.assertEqual(model.read_bytes(), original)
            if name == 'derive':
                (audit / 'derivation.md').write_text('An independent derivation.')
            elif name == 'design':
                self.assertTrue((audit / 'derivation.md').is_file())
                (audit / 'checks.md').write_text('Expected signal and tolerance.')
            elif name == 'review':
                self.assertTrue((audit / 'checks.md').is_file())
                (audit / 'review.md').write_text('The predictor needs repair.')
                if review == 'executable':
                    # Requires an intact starter even when the reviewer edits model.py.
                    (audit / 'test_physics.py').write_text(
                        'from model import Model\n'
                        'def test_signal():\n'
                        '    assert Model is None, "starter fails physics check"\n'
                    )
                model.write_text('invalid reviewer edit!\n')
            else:
                self.assertEqual((audit / 'review.md').read_text(), 'The predictor needs repair.')
                result = audit / 'test-result.json'
                self.assertEqual(result.exists(), review == 'executable')
                if review == 'executable':
                    data = json.loads(result.read_text())
                    self.assertEqual(data['exit_code'], 1, data)
                    self.assertIn('starter fails physics check', data['stdout'])
                    self.assertIn('1 failed', data['stdout'])
                if access == 'delayed' and review == 'executable':
                    # One oracle control exercises the original verifier after repair.
                    shutil.copyfile(SOURCE / 'solution/model.py', model)
                else:
                    break

            # Harbor resets /tests and verifier logs before uploading each step's tests.
            tests = env / 'tests'
            if tests.exists():
                shutil.rmtree(tests)
            shutil.copytree(staged / 'steps' / name / 'tests', tests)
            if name == 'repair':
                result = run_script(tests / 'test.sh', env)
                self.assertEqual((verifier / 'reward.txt').read_text().strip(), '1', result.stdout)
                break
            self.assertFalse((tests / 'test_hidden.py').exists())
            self.assertFalse((tests / 'reference.py').exists())
            (verifier / 'reward.json').unlink(missing_ok=True)
            run_script(tests / 'test.sh', env)
            self.assertEqual(json.loads((verifier / 'reward.json').read_text()), {'audit_artifact': 1})

    def test_repair_can_follow_missing_review_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            staged = root / 'staged'
            shutil.copytree(SOURCE, staged)
            prepare_audit(staged, 'delayed-executable')
            self.assertTrue(all(s.min_reward is None for s in Task(staged).config.steps))

            app = root / 'app'
            (app / 'audit').mkdir(parents=True)
            (root / 'logs/agent').mkdir(parents=True)
            log = root / 'logs/agent/codex.txt'
            def event(kind, message):
                return json.dumps({'type': 'item.completed', 'item': {'type': kind, 'text': message}})

            log.write_text(event('command_execution', 'tool output') + '\n'
                           + event('agent_message', 'Check units of the observed signal.') + '\n')
            shutil.copytree(staged / 'steps/review/tests', root / 'tests')
            run_script(root / 'tests/test.sh', root)
            verifier = root / 'logs/verifier'
            note = (app / 'audit/review.md').read_text()
            self.assertIn('Check units of the observed signal.', note)
            self.assertNotIn('tool output', note)
            self.assertEqual((verifier / 'review.md').read_text(), note)
            self.assertEqual(json.loads((verifier / 'reward.json').read_text()), {'audit_artifact': 0})
            check = app / 'audit/test-result.json'
            record = json.loads(check.read_text())
            self.assertEqual(record['status'], 'not_run')
            self.assertIsNone(record['exit_code'])
            self.assertEqual(check.read_bytes(), (verifier / 'test-result.json').read_bytes())

            (app / 'model.py').write_text('discard previous edit')
            shutil.copytree(staged / 'steps/repair/workdir', app, dirs_exist_ok=True)
            self.assertEqual((app / 'model.py').read_bytes(), (SOURCE / 'environment/model.py').read_bytes())
            self.assertEqual((app / 'audit/review.md').read_text(), note)

    def test_native_workflow(self):
        for access in ('early', 'delayed'):
            for review in ('written', 'executable'):
                with self.subTest(access=access, review=review), tempfile.TemporaryDirectory() as temp:
                    self.check_handoffs(Path(temp), access, review)


if __name__ == '__main__':
    unittest.main()
