"""`read_file` and `grep_files`: the agent reads and searches saved tool outputs, and the
directories a deployment allows, and nothing else. They run over real files under `tmp_path`,
symlinks included."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from surmap.agent.files import file_tools
from surmap.agent.runtime.jobs import Completed, Failed, JobRunner, ToolOutcome
from surmap.agent.runtime.outputs import ToolOutputs
from surmap.agent.runtime.tools import BoundTool

ASSET_LINES = [f'  "asset-{n}": "Debris pile {n}",' for n in range(1, 301)]


class FileRig:
    """The file tools over a runner that saves into `<tmp>/outputs`, plus a folder outside."""

    def __init__(
        self, tmp_path: Path, *, extra_roots: Sequence[Path] = (), max_inline_bytes: int = 16_384
    ) -> None:
        self.outputs = tmp_path / "outputs"
        self.outputs.mkdir()
        self.outside = tmp_path / "outside"
        self.outside.mkdir()
        runner = JobRunner(
            outputs=ToolOutputs(directory=self.outputs, max_inline_bytes=max_inline_bytes)
        )
        self.tools: dict[str, BoundTool] = {
            tool.name: tool for tool in file_tools(runner, extra_roots=extra_roots)
        }

    def saved(self, name: str, lines: Sequence[str]) -> Path:
        path = self.outputs / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    async def call(self, tool: str, **arguments: object) -> ToolOutcome:
        bound = self.tools[tool]
        return await bound.run(bound.prepare(arguments))

    async def result_of(self, tool: str, **arguments: object) -> Mapping[str, object]:
        outcome = await self.call(tool, **arguments)
        assert isinstance(outcome, Completed), outcome
        return outcome.result

    async def refusal_of(self, tool: str, **arguments: object) -> str:
        outcome = await self.call(tool, **arguments)
        assert isinstance(outcome, Failed), outcome
        return outcome.error


def match_lines(result: Mapping[str, object]) -> list[tuple[str, int]]:
    """`(file name, line number)` of every grep match, in order."""
    matches = result["matches"]
    assert isinstance(matches, list)
    return [(Path(str(m["path"])).name, int(m["line"])) for m in matches]


# --- read_file -----------------------------------------------------------------------------


async def test_read_file_returns_a_window_of_numbered_lines_of_a_saved_output(
    tmp_path: Path,
) -> None:
    # Given a saved output of 300 lines
    rig = FileRig(tmp_path)
    rig.saved("j-1-list_assets-ab12.json", ASSET_LINES)

    # When the model reads lines 10 to 12 by the file's name
    result = await rig.result_of("read_file", path="j-1-list_assets-ab12.json", offset=10, limit=3)

    # Then it gets exactly those lines, numbered, and how long the file is
    assert result["content"] == "\n".join(
        [f"10\t{ASSET_LINES[9]}", f"11\t{ASSET_LINES[10]}", f"12\t{ASSET_LINES[11]}"]
    )
    assert (result["start_line"], result["end_line"], result["total_lines"]) == (10, 12, 300)


async def test_read_file_takes_the_absolute_path_a_saved_reference_gives(tmp_path: Path) -> None:
    # Given a saved output
    rig = FileRig(tmp_path)
    path = rig.saved("j-2-get_run-cd34.json", ['{"run_id": "run-7"}'])

    # When the model reads it by its absolute path
    result = await rig.result_of("read_file", path=str(path))

    # Then it reads the file
    assert result["content"] == '1\t{"run_id": "run-7"}'


async def test_read_file_stops_at_the_byte_budget_and_says_where_to_continue(
    tmp_path: Path,
) -> None:
    # Given a saved output, and an inline limit too small for all of it
    rig = FileRig(tmp_path, max_inline_bytes=2_000)
    rig.saved("big.json", ASSET_LINES)

    # When the model reads the whole file
    result = await rig.result_of("read_file", path="big.json", limit=300)

    # Then it gets the lines that fit, is told it was cut short, and where it stopped
    assert result["truncated"] is True
    assert len(str(result["content"]).encode("utf-8")) < 2_000
    assert str(result["content"]).splitlines()[-1].startswith(f"{result['end_line']}\t")


async def test_read_file_refuses_a_path_that_climbs_out_of_the_outputs(tmp_path: Path) -> None:
    # Given a secret next to the outputs folder
    rig = FileRig(tmp_path)
    (rig.outside / "secret.txt").write_text("token\n", encoding="utf-8")

    # When the model reads it through ..
    error = await rig.refusal_of("read_file", path="../outside/secret.txt")

    # Then the read is refused as outside the readable directories
    assert "outside the readable directories" in error


async def test_read_file_refuses_an_absolute_path_outside_the_roots(tmp_path: Path) -> None:
    # Given the file tools
    rig = FileRig(tmp_path)

    # When the model reads a system file
    error = await rig.refusal_of("read_file", path="/etc/passwd")

    # Then the read is refused
    assert "outside the readable directories" in error


async def test_read_file_refuses_a_symlink_inside_the_outputs_that_points_outside(
    tmp_path: Path,
) -> None:
    # Given a link in the outputs folder to a secret outside it
    rig = FileRig(tmp_path)
    (rig.outside / "secret.txt").write_text("token\n", encoding="utf-8")
    (rig.outputs / "innocent.json").symlink_to(rig.outside / "secret.txt")

    # When the model reads the link
    error = await rig.refusal_of("read_file", path="innocent.json")

    # Then the read is refused, because where the link leads is outside
    assert "outside the readable directories" in error


async def test_read_file_reads_a_directory_the_deployment_allows(tmp_path: Path) -> None:
    # Given a deployment that also allows a logs folder
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "agent.log").write_text("started\nready\n", encoding="utf-8")
    rig = FileRig(tmp_path, extra_roots=[logs])

    # When the model reads a log there
    result = await rig.result_of("read_file", path=str(logs / "agent.log"))

    # Then it reads it
    assert result["content"] == "1\tstarted\n2\tready"


async def test_read_file_names_a_missing_file(tmp_path: Path) -> None:
    # Given the file tools
    rig = FileRig(tmp_path)

    # When the model reads a file that was never saved
    error = await rig.refusal_of("read_file", path="j-9-nothing.json")

    # Then the refusal says there is no such file
    assert "no file" in error


async def test_read_file_refuses_a_binary_file(tmp_path: Path) -> None:
    # Given a binary file in the outputs folder
    rig = FileRig(tmp_path)
    (rig.outputs / "frame.jpg").write_bytes(b"\xff\xd8\xff\x00\x10JFIF\x00")

    # When the model reads it
    error = await rig.refusal_of("read_file", path="frame.jpg")

    # Then it is refused as binary
    assert "binary" in error


# --- grep_files ----------------------------------------------------------------------------


async def test_grep_files_finds_matching_lines_with_their_file_and_line_number(
    tmp_path: Path,
) -> None:
    # Given two saved outputs
    rig = FileRig(tmp_path)
    rig.saved("a.json", ['"crate"', '"barrel"', '"crate lid"'])
    rig.saved("b.json", ['"tyre"', '"crate"'])

    # When the model greps every readable file for crate
    result = await rig.result_of("grep_files", pattern="crate")

    # Then each match names its file and line, files in name order
    assert match_lines(result) == [("a.json", 1), ("a.json", 3), ("b.json", 2)]


async def test_grep_files_ignores_case_when_asked(tmp_path: Path) -> None:
    # Given an output with the word in two cases
    rig = FileRig(tmp_path)
    rig.saved("a.json", ['"Crate"', '"crate"'])

    # When the model greps ignoring case
    result = await rig.result_of("grep_files", pattern="crate", ignore_case=True)

    # Then both lines match
    assert match_lines(result) == [("a.json", 1), ("a.json", 2)]


async def test_grep_files_searches_only_files_matching_the_glob(tmp_path: Path) -> None:
    # Given a json and a text output that both mention crate
    rig = FileRig(tmp_path)
    rig.saved("a.json", ['"crate"'])
    rig.saved("notes.txt", ["crate"])

    # When the model greps only json files
    result = await rig.result_of("grep_files", pattern="crate", glob="*.json")

    # Then only the json file is searched
    assert match_lines(result) == [("a.json", 1)]


async def test_grep_files_stops_at_max_matches_and_says_so(tmp_path: Path) -> None:
    # Given an output with 300 matching lines
    rig = FileRig(tmp_path)
    rig.saved("big.json", ASSET_LINES)

    # When the model asks for at most five matches
    result = await rig.result_of("grep_files", pattern="Debris", max_matches=5)

    # Then it gets the first five and is told there were more
    assert match_lines(result) == [("big.json", n) for n in range(1, 6)]
    assert result["truncated"] is True


async def test_grep_files_does_not_follow_a_symlinked_folder_out_of_the_roots(
    tmp_path: Path,
) -> None:
    # Given a link in the outputs folder to a folder outside it holding a secret
    rig = FileRig(tmp_path)
    (rig.outside / "secret.txt").write_text("token=hunter2\n", encoding="utf-8")
    (rig.outputs / "linked").symlink_to(rig.outside, target_is_directory=True)

    # When the model greps everything for the token
    result = await rig.result_of("grep_files", pattern="hunter2")

    # Then nothing outside is found
    assert match_lines(result) == []


async def test_grep_files_refuses_a_path_outside_the_roots(tmp_path: Path) -> None:
    # Given the file tools
    rig = FileRig(tmp_path)

    # When the model greps a folder outside
    error = await rig.refusal_of("grep_files", pattern="root", path="/etc")

    # Then it is refused
    assert "outside the readable directories" in error


async def test_grep_files_names_an_invalid_pattern(tmp_path: Path) -> None:
    # Given the file tools
    rig = FileRig(tmp_path)

    # When the model greps with a broken regular expression
    error = await rig.refusal_of("grep_files", pattern="crate(")

    # Then the refusal says the pattern is invalid
    assert "invalid pattern" in error


async def test_grep_files_skips_binary_files(tmp_path: Path) -> None:
    # Given a binary file that happens to contain the word
    rig = FileRig(tmp_path)
    (rig.outputs / "frame.jpg").write_bytes(b"\xff\xd8\x00crate\x00")

    # When the model greps for it
    result = await rig.result_of("grep_files", pattern="crate")

    # Then the binary file is not matched
    assert match_lines(result) == []


def test_the_file_tools_are_never_saved_to_a_file_on_their_own(tmp_path: Path) -> None:
    # Given the file tools
    rig = FileRig(tmp_path)

    # When their binding is read
    saving = {name: tool.saves_large_results for name, tool in rig.tools.items()}

    # Then neither spills its result into another file
    assert saving == {"read_file": False, "grep_files": False}
