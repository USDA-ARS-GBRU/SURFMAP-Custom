from pathlib import Path
import os
import subprocess
import sys
from typing import List

from surfmap import SURFMAP_DOCKER_VERSION, DOCKER_REPOSITORY


class DockerCLI:
    DOCKER_REPOSITORY = DOCKER_REPOSITORY
    TAG = SURFMAP_DOCKER_VERSION

    def __init__(self, args, input_args: List[str], output_args: str, out_dirname: str, input_dir: str='/home/surfmap/input', output_dir: str='/home/surfmap/output') -> None:
        self.cli = ['docker', 'run', '--rm']
        # run as the invoking host user instead of the image's baked-in
        # "surfmap" user, so writes to the bind-mounted output directory
        # succeed regardless of the host's uid/gid - it only happened to work
        # before on hosts where the user is coincidentally uid 1000 (the
        # image's fixed "surfmap" uid), e.g. most single-user Linux desktops,
        # but not e.g. CI runners or shared servers.
        self.cli += ['--user', f'{os.getuid()}:{os.getgid()}']
        if sys.stdin.isatty():
            # only request a pseudo-tty when one is actually available, otherwise
            # docker fails with "the input device is not a TTY" (CI, scripts, pipes, ...)
            self.cli += ['-it']

        self.prog = Path(sys.argv[0]).name
        self.input_args = input_args
        self.output_args = output_args
        self.input_dir = input_dir
        self.output_dir = output_dir

        self.input_files = [getattr(args, x.replace("-", "")) for x in self.input_args]
        self.container_input_paths: List[str] = []
        self.output = out_dirname
        Path(self.output).mkdir(exist_ok=True, parents=True)

        self._set_cli()

    def _set_cli(self):
        self.cli += self._mounting_points() + [f"{self.DOCKER_REPOSITORY}:{self.TAG}"] + [self.prog] + self._arguments()

    def _mounting_points(self):
        mnt_point = []
        for i, input_file in enumerate(self.input_files):
            # prefix with the index to avoid collisions when two input files
            # (e.g. -pdb and -res) share the same basename from different dirs
            container_path = f"{self.input_dir}/{i}_{Path(input_file).name}"
            self.container_input_paths.append(container_path)
            mnt_point += ["-v", f"{Path(input_file).resolve()}:{container_path}:ro"]

        mnt_point += ["-v", f"{Path(self.output).resolve()}:{self.output_dir}:rw"]

        return mnt_point

    def _arguments(self):
        cmd_arguments = []

        # add all surfmap command line arguments except --docker
        for argv in sys.argv[1:]:
            if argv == "--docker":
                continue
            cmd_arguments.append(argv)

        # edit arguments relative to input(s)
        for i, input_arg in enumerate(self.input_args):
            cmd_arguments[cmd_arguments.index(input_arg) + 1] = self.container_input_paths[i]

        # edit arguments relative to output
        if self.output_args in cmd_arguments:
            cmd_arguments[cmd_arguments.index(self.output_args) + 1] = self.output_dir
        else:
            cmd_arguments += [self.output_args, self.output_dir]

        return cmd_arguments


    def cmd(self):
        return " ".join(self.cli)

    def show(self):
        print(f"\n{self.cmd()}\n")

    def run(self):
        """Run the docker container and return its exit code so callers can propagate it."""
        return subprocess.call(self.cli)
