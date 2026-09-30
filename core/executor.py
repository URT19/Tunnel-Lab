import subprocess

class Executor:
    def __init__(self, dry_run=False, logger=None):
        self.dry_run = dry_run
        self.logger = logger

    def run(self, cmd, check=False):
        if self.logger:
            self.logger.info(f"RUN: {cmd}")
        if self.dry_run:
            return 0, "", ""
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if check and p.returncode != 0:
            raise RuntimeError(f"cmd failed: {cmd}\n{p.stderr}")
        return p.returncode, p.stdout, p.stderr