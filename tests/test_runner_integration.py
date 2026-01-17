"""Integration tests for the Claude Code runner."""

import tempfile
from pathlib import Path

import pytest

from ralph_py_cli.utils.claude_runner import (
    RunStatus,
    build_iteration_prompt,
    parse_claude_output,
    run_claude_iteration,
)


class TestBuildIterationPrompt:
    """Tests for build_iteration_prompt function."""

    def test_includes_plan_text(self):
        """Test that the prompt includes the plan text."""
        plan = "Build a calculator app"
        prompt = build_iteration_prompt(plan)

        assert "Build a calculator app" in prompt

    def test_has_plan_tags(self):
        """Test that the prompt wraps plan in XML tags."""
        prompt = build_iteration_prompt("test plan")

        assert "<plan>" in prompt
        assert "</plan>" in prompt

    def test_has_completion_marker_instruction(self):
        """Test that the prompt instructs to use completion marker."""
        prompt = build_iteration_prompt("test plan")

        assert "<Completed>" in prompt

    def test_has_improved_marker_instruction(self):
        """Test that the prompt instructs to use improved marker."""
        prompt = build_iteration_prompt("test plan")

        assert "<Improved>" in prompt

    def test_explains_both_markers(self):
        """Test that the prompt explains when to use each marker."""
        prompt = build_iteration_prompt("test plan")

        # Should mention both markers
        assert "<Improved>" in prompt
        assert "<Completed>" in prompt
        # Should explain when to use each
        assert "progress" in prompt.lower() or "not yet" in prompt.lower()
        assert "fully" in prompt.lower() or "finished" in prompt.lower()

    def test_emphasizes_one_task(self):
        """Test that the prompt emphasizes picking one task."""
        prompt = build_iteration_prompt("test plan")

        assert "ONE" in prompt


class TestParseClaudeOutput:
    """Tests for parse_claude_output function."""

    def test_with_completed_marker(self):
        """Test parsing output that contains the completed marker."""
        raw_output = '{"result": "I made some changes. <Completed>Added the new feature successfully</Completed> All done."}'

        marker_type, output_message, summary = parse_claude_output(raw_output)

        assert marker_type == "completed"
        assert output_message == "Added the new feature successfully"
        assert summary == "Added the new feature successfully"

    def test_with_improved_marker(self):
        """Test parsing output that contains the improved marker."""
        raw_output = '{"result": "Making progress. <Improved>Added half the feature, more work needed</Improved>"}'

        marker_type, output_message, summary = parse_claude_output(raw_output)

        assert marker_type == "improved"
        assert output_message == "Added half the feature, more work needed"
        assert summary == "Added half the feature, more work needed"

    def test_completed_takes_precedence(self):
        """Test that <Completed> takes precedence when both markers present."""
        raw_output = '{"result": "<Improved>partial</Improved> <Completed>finished</Completed>"}'

        marker_type, output_message, summary = parse_claude_output(raw_output)

        assert marker_type == "completed"
        assert output_message == "finished"

    def test_without_marker(self):
        """Test parsing output that lacks any marker."""
        raw_output = '{"result": "I made some changes but forgot the marker."}'

        marker_type, output_message, summary = parse_claude_output(raw_output)

        assert marker_type is None
        assert output_message is None
        assert len(summary) > 0

    def test_invalid_json_with_completed(self):
        """Test parsing non-JSON output with completed marker."""
        raw_output = "This is not JSON but has <Completed>a marker</Completed> in it."

        marker_type, output_message, summary = parse_claude_output(raw_output)

        assert marker_type == "completed"
        assert output_message == "a marker"

    def test_invalid_json_with_improved(self):
        """Test parsing non-JSON output with improved marker."""
        raw_output = "This is not JSON but has <Improved>made progress</Improved> in it."

        marker_type, output_message, summary = parse_claude_output(raw_output)

        assert marker_type == "improved"
        assert output_message == "made progress"

    def test_multiline_marker(self):
        """Test parsing output with multiline content in the marker."""
        raw_output = """{"result": "Done! <Completed>
Made the following changes:
- Added file A
- Modified file B
</Completed>"}"""

        marker_type, output_message, summary = parse_claude_output(raw_output)

        assert marker_type == "completed"
        assert output_message is not None
        assert "Added file A" in output_message
        assert "Modified file B" in output_message


class TestRunClaudeIteration:
    """Tests for run_claude_iteration function."""

    async def test_invalid_folder(self):
        """Test with a non-existent folder."""
        result = await run_claude_iteration(
            plan_text="Do something.",
            folder_path="/nonexistent/path/that/does/not/exist",
            timeout_seconds=10.0,
        )

        assert result.status == RunStatus.PROCESS_ERROR
        assert "does not exist" in result.error_message

    async def test_path_is_file_not_directory(self, tmp_path):
        """Test with a path that is a file, not a directory."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        result = await run_claude_iteration(
            plan_text="Do something.",
            folder_path=str(test_file),
            timeout_seconds=10.0,
        )

        assert result.status == RunStatus.PROCESS_ERROR
        assert "not a directory" in result.error_message


@pytest.mark.slow
@pytest.mark.integration
class TestRunClaudeIterationIntegration:
    """Integration tests that require Claude CLI."""

    async def test_number_addition(self):
        """Integration test: Claude adds a number and reports count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            numbers_file = Path(tmpdir) / "numbers.txt"
            numbers_file.write_text("1\n2\n3\n")

            result = await run_claude_iteration(
                plan_text="Add a new number to numbers.txt (the next number in sequence) and tell me how many numbers are currently in the document.",
                folder_path=tmpdir,
                timeout_seconds=120.0,
            )

            # Check the file was modified
            new_content = numbers_file.read_text()

            # Should return IMPROVED or COMPLETED (both are valid success states)
            assert result.status in (RunStatus.IMPROVED, RunStatus.COMPLETED), f"Expected IMPROVED or COMPLETED, got {result.status}: {result.error_message}"
            assert "4" in new_content, f"Expected '4' to be added to file, got: {new_content!r}"
            assert "4" in result.output_message or "four" in result.output_message.lower(), "Expected count in output"

    async def test_empty_file(self):
        """Test with an empty numbers file - Claude should add 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            numbers_file = Path(tmpdir) / "numbers.txt"
            numbers_file.write_text("")

            result = await run_claude_iteration(
                plan_text="Add a new number to numbers.txt (the next number in sequence, starting from 1 if empty) and tell me how many numbers are currently in the document.",
                folder_path=tmpdir,
                timeout_seconds=120.0,
            )

            new_content = numbers_file.read_text()

            # Should return IMPROVED or COMPLETED (both are valid success states)
            assert result.status in (RunStatus.IMPROVED, RunStatus.COMPLETED), f"Expected IMPROVED or COMPLETED, got {result.status}: {result.error_message}"
            assert "1" in new_content, f"Expected '1' to be added to empty file, got: {new_content!r}"

    async def test_add_number_five_completion(self):
        """Integration test: Simple definite task should return COMPLETED.

        This test verifies that a simple, clearly completable task results in
        the COMPLETED status rather than IMPROVED.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            doc_file = Path(tmpdir) / "document.txt"
            doc_file.write_text("This document contains some numbers: 1, 2, 3, 4\n")

            result = await run_claude_iteration(
                plan_text="Add the number five to document.txt. This is the complete task - just add the number 5 somewhere in the document.",
                folder_path=tmpdir,
                timeout_seconds=120.0,
            )

            new_content = doc_file.read_text()

            assert result.status == RunStatus.COMPLETED, f"Expected COMPLETED for simple definite task, got {result.status}: {result.error_message}"
            assert "5" in new_content, f"Expected '5' to be in file, got: {new_content!r}"

    async def test_timeout(self):
        """Test that timeout works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            result = await run_claude_iteration(
                plan_text="Do a complex analysis of the entire codebase.",
                folder_path=tmpdir,
                timeout_seconds=0.1,  # 100ms - too short for any real work
            )

            assert result.status == RunStatus.TIMEOUT, f"Expected TIMEOUT, got {result.status}"
