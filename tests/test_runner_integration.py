"""Integration tests for the agent runner."""

import tempfile
from pathlib import Path

import pytest

from ralph_py_cli.utils.agents.base import RunStatus
from ralph_py_cli.utils.agents.claude import ClaudeAgent
from ralph_py_cli.utils.agent_runner import (
    check_agent_available,
    get_agent,
    run_agent_iteration,
)


class TestAgentFactory:
    """Tests for agent factory function."""

    def test_get_claude_agent(self):
        """Test getting claude agent."""
        agent = get_agent("claude")
        assert agent.name == "claude"

    def test_get_opencode_agent(self):
        """Test getting opencode agent."""
        agent = get_agent("opencode")
        assert agent.name == "opencode"

    def test_unknown_agent_raises(self):
        """Test unknown agent type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown agent type"):
            get_agent("unknown")


class TestAgentAvailability:
    """Tests for agent availability checking."""

    def test_check_claude_available(self):
        """Test checking if claude is available."""
        available, error = check_agent_available("claude")
        # May or may not be available depending on environment
        if available:
            assert error is None
        else:
            assert error is not None
            assert "claude" in error.lower()

    def test_check_unknown_agent(self):
        """Test checking unknown agent returns error."""
        available, error = check_agent_available("unknown")
        assert available is False
        assert "Unknown agent type" in error


class TestBuildIterationPrompt:
    """Tests for build_iteration_prompt function."""

    def test_includes_plan_text(self):
        """Test that the prompt includes the plan text."""
        agent = ClaudeAgent()
        plan = "Build a calculator app"
        prompt = agent._build_iteration_prompt(plan)

        assert "Build a calculator app" in prompt

    def test_has_plan_tags(self):
        """Test that the prompt wraps plan in XML tags."""
        agent = ClaudeAgent()
        prompt = agent._build_iteration_prompt("test plan")

        assert "<plan>" in prompt
        assert "</plan>" in prompt

    def test_has_completion_marker_instruction(self):
        """Test that the prompt instructs to use completion marker."""
        agent = ClaudeAgent()
        prompt = agent._build_iteration_prompt("test plan")

        assert "<Completed>" in prompt

    def test_has_improved_marker_instruction(self):
        """Test that the prompt instructs to use improved marker."""
        agent = ClaudeAgent()
        prompt = agent._build_iteration_prompt("test plan")

        assert "<Improved>" in prompt

    def test_explains_both_markers(self):
        """Test that the prompt explains when to use each marker."""
        agent = ClaudeAgent()
        prompt = agent._build_iteration_prompt("test plan")

        # Should mention both markers
        assert "<Improved>" in prompt
        assert "<Completed>" in prompt
        # Should explain when to use each
        assert "progress" in prompt.lower() or "not yet" in prompt.lower()
        assert "fully" in prompt.lower() or "finished" in prompt.lower()

    def test_emphasizes_one_task(self):
        """Test that the prompt emphasizes picking one task."""
        agent = ClaudeAgent()
        prompt = agent._build_iteration_prompt("test plan")

        assert "ONE" in prompt


class TestParseClaudeOutput:
    """Tests for parse_claude_output function."""

    def test_with_completed_marker(self):
        """Test parsing output that contains the completed marker."""
        agent = ClaudeAgent()
        raw_output = '{"result": "I made some changes. <Completed>Added the new feature successfully</Completed> All done."}'

        marker_type, output_message, summary, _token_usage = agent.parse_output(raw_output)

        assert marker_type == "completed"
        assert output_message == "Added the new feature successfully"
        assert summary == "Added the new feature successfully"

    def test_with_improved_marker(self):
        """Test parsing output that contains the improved marker."""
        agent = ClaudeAgent()
        raw_output = '{"result": "Making progress. <Improved>Added half the feature, more work needed</Improved>"}'

        marker_type, output_message, summary, _token_usage = agent.parse_output(raw_output)

        assert marker_type == "improved"
        assert output_message == "Added half the feature, more work needed"
        assert summary == "Added half the feature, more work needed"

    def test_completed_takes_precedence(self):
        """Test that <Completed> takes precedence when both markers present."""
        agent = ClaudeAgent()
        raw_output = '{"result": "<Improved>partial</Improved> <Completed>finished</Completed>"}'

        marker_type, output_message, summary, _token_usage = agent.parse_output(raw_output)

        assert marker_type == "completed"
        assert output_message == "finished"

    def test_without_marker(self):
        """Test parsing output that lacks any marker."""
        agent = ClaudeAgent()
        raw_output = '{"result": "I made some changes but forgot the marker."}'

        marker_type, output_message, summary, _token_usage = agent.parse_output(raw_output)

        assert marker_type is None
        assert output_message is None
        assert len(summary) > 0

    def test_invalid_json_with_completed(self):
        """Test parsing non-JSON output with completed marker."""
        agent = ClaudeAgent()
        raw_output = "This is not JSON but has <Completed>a marker</Completed> in it."

        marker_type, output_message, summary, _token_usage = agent.parse_output(raw_output)

        assert marker_type == "completed"
        assert output_message == "a marker"

    def test_invalid_json_with_improved(self):
        """Test parsing non-JSON output with improved marker."""
        agent = ClaudeAgent()
        raw_output = "This is not JSON but has <Improved>made progress</Improved> in it."

        marker_type, output_message, summary, _token_usage = agent.parse_output(raw_output)

        assert marker_type == "improved"
        assert output_message == "made progress"

    def test_multiline_marker(self):
        """Test parsing output with multiline content in the marker."""
        agent = ClaudeAgent()
        raw_output = """{"result": "Done! <Completed>
Made the following changes:
- Added file A
- Modified file B
</Completed>"}"""

        marker_type, output_message, summary, _token_usage = agent.parse_output(raw_output)

        assert marker_type == "completed"
        assert output_message is not None
        assert "Added file A" in output_message
        assert "Modified file B" in output_message


class TestRunAgentIteration:
    """Tests for run_agent_iteration function."""

    def test_invalid_folder(self):
        """Test with a non-existent folder."""
        result = run_agent_iteration(
            agent_type="claude",
            plan_text="Do something.",
            folder_path="/nonexistent/path/that/does/not/exist",
            timeout_seconds=10.0,
        )

        assert result.status == RunStatus.PROCESS_ERROR
        assert "does not exist" in result.error_message

    def test_path_is_file_not_directory(self, tmp_path):
        """Test with a path that is a file, not a directory."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        result = run_agent_iteration(
            agent_type="claude",
            plan_text="Do something.",
            folder_path=str(test_file),
            timeout_seconds=10.0,
        )

        assert result.status == RunStatus.PROCESS_ERROR
        assert "not a directory" in result.error_message

    def test_unknown_agent_type(self, tmp_path):
        """Test with unknown agent type."""
        result = run_agent_iteration(
            agent_type="unknown",
            plan_text="Do something.",
            folder_path=str(tmp_path),
            timeout_seconds=10.0,
        )

        assert result.status == RunStatus.PROCESS_ERROR
        assert "Unknown agent type" in result.error_message


@pytest.mark.slow
@pytest.mark.integration
class TestRunAgentIterationIntegration:
    """Integration tests that require agent CLIs."""

    def test_claude_number_addition(self):
        """Integration test: Claude adds a number and reports count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            numbers_file = Path(tmpdir) / "numbers.txt"
            numbers_file.write_text("1\n2\n3\n")

            result = run_agent_iteration(
                agent_type="claude",
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

    def test_claude_empty_file(self):
        """Test with an empty numbers file - Claude should add 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            numbers_file = Path(tmpdir) / "numbers.txt"
            numbers_file.write_text("")

            result = run_agent_iteration(
                agent_type="claude",
                plan_text="Add a new number to numbers.txt (the next number in sequence, starting from 1 if empty) and tell me how many numbers are currently in the document.",
                folder_path=tmpdir,
                timeout_seconds=120.0,
            )

            new_content = numbers_file.read_text()

            # Should return IMPROVED or COMPLETED (both are valid success states)
            assert result.status in (RunStatus.IMPROVED, RunStatus.COMPLETED), f"Expected IMPROVED or COMPLETED, got {result.status}: {result.error_message}"
            assert "1" in new_content, f"Expected '1' to be added to empty file, got: {new_content!r}"

    def test_claude_add_number_five_completion(self):
        """Integration test: Simple definite task should return COMPLETED.

        This test verifies that a simple, clearly completable task results in
        the COMPLETED status rather than IMPROVED.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            doc_file = Path(tmpdir) / "document.txt"
            doc_file.write_text("This document contains some numbers: 1, 2, 3, 4\n")

            result = run_agent_iteration(
                agent_type="claude",
                plan_text="Add the number five to document.txt. This is the complete task - just add the number 5 somewhere in the document.",
                folder_path=tmpdir,
                timeout_seconds=120.0,
            )

            new_content = doc_file.read_text()

            assert result.status == RunStatus.COMPLETED, f"Expected COMPLETED for simple definite task, got {result.status}: {result.error_message}"
            assert "5" in new_content, f"Expected '5' to be in file, got: {new_content!r}"

    def test_timeout(self):
        """Test that timeout works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            result = run_agent_iteration(
                agent_type="claude",
                plan_text="Do a complex analysis of the entire codebase.",
                folder_path=tmpdir,
                timeout_seconds=0.1,  # 100ms - too short for any real work
            )

            assert result.status == RunStatus.TIMEOUT, f"Expected TIMEOUT, got {result.status}"


@pytest.mark.slow
@pytest.mark.integration
class TestRunEndlesslyIntegration:
    """Integration tests for the run_endlessly command."""

    def test_run_endlessly_with_max_iterations(self):
        """Test that run_endlessly stops at max_iterations count."""
        from ralph_py_cli.cli import run_endless_loop
        from ralph_py_cli.utils.interactive import LoopState

        with tempfile.TemporaryDirectory() as tmpdir:
            numbers_file = Path(tmpdir) / "numbers.txt"
            numbers_file.write_text("1\n2\n3\n")

            state = LoopState(
                plan_text="Add a new number to numbers.txt (the next number in sequence).",
                total_iterations=999999,
                agent_type="claude",
            )

            iterations_run, status, message = run_endless_loop(
                folder=Path(tmpdir),
                state=state,
                timeout=120.0,
                model=None,
                verbose=False,
                max_iterations=2,
            )

            assert iterations_run == 2, f"Expected 2 iterations, got {iterations_run}"
            assert "max_iterations reached" in message.lower()

    def test_run_endlessly_continues_on_completed(self):
        """Test that run_endlessly continues past COMPLETED marker."""
        from ralph_py_cli.cli import run_endless_loop
        from ralph_py_cli.utils.interactive import LoopState

        with tempfile.TemporaryDirectory() as tmpdir:
            doc_file = Path(tmpdir) / "document.txt"
            doc_file.write_text("Count: 0\n")

            state = LoopState(
                plan_text="Increment the count in document.txt by 1. This is a complete, simple task.",
                total_iterations=999999,
                agent_type="claude",
            )

            iterations_run, status, message = run_endless_loop(
                folder=Path(tmpdir),
                state=state,
                timeout=120.0,
                model=None,
                verbose=False,
                max_iterations=3,
            )

            # Should run all 3 iterations even if some complete
            assert iterations_run == 3, f"Expected 3 iterations, got {iterations_run}"
            assert "max_iterations reached" in message.lower()

            # Verify the file was modified multiple times
            content = doc_file.read_text()
            # After 3 iterations, count should be at least 1 (probably higher)
            assert "1" in content or "2" in content or "3" in content

    def test_run_endlessly_continues_on_missing_marker(self):
        """Test that run_endlessly continues with warning on MISSING_MARKER."""
        from ralph_py_cli.cli import run_endless_loop
        from ralph_py_cli.utils.interactive import LoopState

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("content")

            # Use a vague plan that might not always trigger markers
            state = LoopState(
                plan_text="Look at test.txt.",
                total_iterations=999999,
                agent_type="claude",
            )

            iterations_run, status, message = run_endless_loop(
                folder=Path(tmpdir),
                state=state,
                timeout=120.0,
                model=None,
                verbose=False,
                max_iterations=2,
            )

            # Should complete all iterations regardless of markers
            assert iterations_run == 2, f"Expected 2 iterations, got {iterations_run}"
            assert "max_iterations reached" in message.lower()

    def test_run_endlessly_stops_on_consecutive_errors(self):
        """Test that run_endlessly stops after 3 consecutive timeouts."""
        from ralph_py_cli.cli import run_endless_loop
        from ralph_py_cli.utils.interactive import LoopState

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            state = LoopState(
                plan_text="Do a very complex analysis of the entire codebase that will timeout.",
                total_iterations=999999,
                agent_type="claude",
            )

            iterations_run, status, message = run_endless_loop(
                folder=Path(tmpdir),
                state=state,
                timeout=0.1,  # Very short timeout to force failures
                model=None,
                verbose=False,
                max_iterations=10,  # Set high max but should stop on errors
            )

            # Should stop after 3 consecutive timeouts
            assert iterations_run == 3, f"Expected 3 iterations (3 consecutive errors), got {iterations_run}"
            assert status == RunStatus.TIMEOUT
            assert "consecutive errors" in message.lower()
