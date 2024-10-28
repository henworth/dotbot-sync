import grp
import os
import pwd
import subprocess
from glob import glob

import dotbot


class Sync(dotbot.Plugin):
    """
    Sync dotfiles
    """

    _directive = "sync"

    def can_handle(self, directive):
        return directive == self._directive

    def handle(self, directive, data):
        if directive != self._directive:
            raise ValueError(f"Sync cannot handle directive {directive}")
        return self._process_records(data)

    def _chmodown(self, path, chmod, uid, gid):
        os.chmod(path, chmod)
        os.chown(path, uid, gid)

    @staticmethod
    def expand_path(path, globs=False):
        path = os.path.expanduser(path)
        path = os.path.expandvars(path)
        return glob(path) if globs else [path]

    def _process_records(self, records):
        success = True
        defaults = self._context.defaults().get("sync", {})

        with open(os.devnull, "w"):
            for destination, source in records.items():
                destination = Sync.expand_path(destination, globs=False)
                rsync = defaults.get("rsync", "rsync")
                options = defaults.get("options", ["--delete", "--safe-links"])
                create = defaults.get("create", False)
                fmode = defaults.get("fmode", 644)
                dmode = defaults.get("dmode", 755)
                owner = defaults.get("owner", pwd.getpwuid(os.getuid()).pw_name)
                group = defaults.get("group", grp.getgrgid(os.getgid()).gr_name)

                if isinstance(source, dict):
                    # extended config
                    create = source.get("create", create)
                    rsync = source.get("rsync", rsync)
                    options = source.get("options", options)
                    fmode = source.get("fmode", fmode)
                    dmode = source.get("dmode", dmode)
                    owner = source.get("owner", owner)
                    group = source.get("group", group)
                    paths_expression = source["path"]
                else:
                    paths_expression = source

                uid = pwd.getpwnam(owner).pw_uid
                gid = grp.getgrnam(group).gr_gid

                if create:
                    success &= self._create(destination, int(str(dmode), 8), uid, gid)

                paths = Sync.expand_path(paths_expression, globs=True)

                if len(paths) > 1:
                    self._log.lowinfo(
                        f"Synchronizing expression {paths_expression} -> {destination}"
                    )

                for path in paths:
                    success &= self._sync(
                        path,
                        destination,
                        dmode,
                        fmode,
                        owner,
                        group,
                        rsync,
                        options,
                    )

        if success:
            self._log.info("All synchronizations have been done")
        else:
            self._log.error("Some synchronizations were not successful")
        return success

    def _create(self, path, dmode, uid, gid):
        success = True
        parent = os.path.abspath(os.path.join(path, os.pardir))
        if not os.path.exists(parent):
            try:
                os.mkdir(parent, dmode)
                self._chmodown(parent, dmode, uid, gid)
            except Exception as e:
                self._log.warning(f"Failed to create directory {parent}. {e}")
                success = False
            else:
                self._log.lowinfo(f"Creating directory {parent}")
        return success

    def _sync(
        self,
        source,
        destination,
        dmode,
        fmode,
        owner,
        group,
        rsync,
        options,
    ):
        """
        Synchronizes source to destination

        Returns true if successfully synchronized files.
        """
        success = False
        source = os.path.join(self._context.base_directory(), source)
        destination = os.path.expanduser(destination)
        try:
            cmd = [
                rsync,
                "--update",
                "--recursive",
                "--group",
                "--owner",
                f"--chown={owner}:{group}",
                f"--chmod=D{dmode},F{fmode}",
            ]
            if os.path.isdir(source):
                source = f"{source}/"
            try:
                cmd += options + [f'"{source}"', f'"{destination}"']
                subprocess.run(
                    " ".join(cmd),
                    shell=True,
                    check=True,
                    capture_output=True,
                    cwd=self._context.base_directory(),
                )
            except subprocess.CalledProcessError as e:
                self._log.warning(f"Failed to sync {source} -> {destination}. {e}")
            else:
                success = True
                self._log.lowinfo(f"Synchronized {source} -> {destination}")
        except Exception as e:
            self._log.warning(f"Failed to sync {source} -> {destination}. {e}")
        return success
