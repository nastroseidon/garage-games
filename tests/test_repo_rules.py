"""Git rules for the Unreal project: what is ignored, what goes to Git LFS,
and a guard against big binaries sneaking into the repo.

The rule tests build a throwaway git repo with this project's .gitignore and
.gitattributes, create real example files, commit them, and look at what
git kept, what it ignored and what it stored in LFS. Skipped when git (or
Git LFS) isn't installed.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIT = shutil.which("git")
UE = "unreal/GarageGames/"
MAX_PLAIN_FILE = 5 * 1024 * 1024  # anything bigger belongs in Git LFS

IGNORED = [
    UE + "Binaries/Win64/UnrealEditor-GarageGames.dll",
    UE + "Intermediate/ProjectFiles/GarageGames.vcxproj",
    UE + "Saved/Logs/GarageGames.log",
    UE + "DerivedDataCache/Compressed.ddp",
    UE + "Plugins/ShotBridge/Binaries/Win64/x.dll",
    UE + "Plugins/ShotBridge/Intermediate/Build/x.obj",
    UE + "Build/Windows/GarageGames.exe",
    UE + "GarageGames.sln",
    UE + ".vs/GarageGames/v17/.suo",
    UE + "Content/Fab/Rock/SM_Rock.uasset",
    UE + "Content/Megascans/Surfaces/Grass/T_Grass_D.uasset",
    UE + "Content/ThirdParty/Trees/SM_Oak.uasset",
    UE + "Content/StarterContent/Props/SM_Chair.uasset",
    UE + "Plugins/Marketplace/CoolPack/CoolPack.uplugin",
    "UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe",
    "UnrealEngine/Engine/Source/Runtime/Core/Core.Build.cs",
]
IN_LFS = [
    UE + "Content/Maps/Range.umap",
    UE + "Content/Garage/BP_ShotPlayer.uasset",
    UE + "Content/Garage/T_Ball.ubulk",
    UE + "Content/Garage/T_Ball.uexp",
    UE + "Art/ball.fbx",
    UE + "Art/turf.png",
    UE + "Audio/crowd.wav",
]
PLAIN = [
    UE + "GarageGames.uproject",
    UE + "Config/DefaultEngine.ini",
    UE + "Content/Python/play_shot.py",
    UE + "Source/GarageGames/GarageGames.Build.cs",
    UE + "Plugins/ShotBridge/ShotBridge.uplugin",
    "web/icon.png",
    "web/app.js",
    "server.py",
]


def run(args, cwd, **kw):
    return subprocess.run([GIT, *args], cwd=cwd, capture_output=True, text=True, **kw)


def has_lfs():
    return GIT is not None and run(["lfs", "version"], ROOT).returncode == 0


def is_repo():
    return GIT is not None and run(["rev-parse", "--git-dir"], ROOT).returncode == 0


@unittest.skipUnless(has_lfs(), "needs git and Git LFS")
class RepoRuleTests(unittest.TestCase):
    """Commit example files into a scratch repo that uses our rules."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        repo = cls.tmp.name
        for args in (["init", "-q"], ["config", "user.name", "test"], ["config", "user.email", "test@example.com"],
                     ["config", "core.autocrlf", "false"], ["lfs", "install", "--local"]):
            run(args, repo, check=True)
        for name in (".gitignore", ".gitattributes"):
            shutil.copy(os.path.join(ROOT, name), os.path.join(repo, name))
        for path in IGNORED + IN_LFS + PLAIN:
            full = os.path.join(repo, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as f:
                f.write(b"example " + path.encode() + b"\n")
        run(["add", "-A"], repo, check=True)
        run(["commit", "-q", "-m", "example"], repo, check=True)
        cls.committed = set(run(["ls-files"], repo, check=True).stdout.split())
        cls.lfs = set(run(["lfs", "ls-files", "--name-only"], repo, check=True).stdout.split("\n")) - {""}
        cls.repo = repo

    @classmethod
    def tearDownClass(cls):
        try:
            cls.tmp.cleanup()
        except OSError:
            pass  # Windows sometimes keeps a lock on .git files for a moment

    def test_generated_and_third_party_files_are_ignored(self):
        self.assertEqual(sorted(set(IGNORED) & self.committed), [], "these should be ignored")

    def test_project_files_are_kept(self):
        self.assertEqual(sorted(set(IN_LFS + PLAIN) - self.committed), [], "these must be committed")

    def test_unreal_binaries_go_to_lfs(self):
        self.assertEqual(sorted(set(IN_LFS) - self.lfs), [], "should be stored in LFS")
        self.assertEqual(sorted(set(PLAIN) & self.lfs), [], "should stay ordinary files")
        # the repo itself only holds a small pointer to the real file
        pointer = run(["show", "HEAD:" + IN_LFS[0]], self.repo, check=True).stdout
        self.assertTrue(pointer.startswith("version https://git-lfs.github.com/spec/v1"), pointer[:80])


@unittest.skipUnless(is_repo(), "needs git and a git checkout")
class CommittedFilesTests(unittest.TestCase):
    def test_no_big_or_unreal_binary_files_committed_outside_lfs(self):
        lfs_files = set(run(["lfs", "ls-files", "--name-only"], ROOT).stdout.split("\n"))
        for path in run(["ls-files", "-z"], ROOT, check=True).stdout.split("\0"):
            full = os.path.join(ROOT, path)
            if not path or path in lfs_files or not os.path.isfile(full):
                continue
            self.assertLess(os.path.getsize(full), MAX_PLAIN_FILE, path + " is big: put it in Git LFS")
            self.assertFalse(path.lower().endswith((".uasset", ".umap", ".ubulk", ".uexp")),
                             path + " is an Unreal asset outside Git LFS")
            for part in ("/Binaries/", "/Intermediate/", "/Saved/", "/DerivedDataCache/", "/Content/Fab/",
                         "/Content/Megascans/", "/Content/StarterContent/"):
                self.assertNotIn(part, "/" + path, path + " should not be committed")


if __name__ == "__main__":
    unittest.main()
