"""Unit tests for FileSystemTool -- uses tmp_path for isolation."""
import pytest
from signalagent.tools.builtins.file_system import FileSystemTool


@pytest.fixture
def tool(tmp_path):
    return FileSystemTool(root=tmp_path)


class TestFileSystemToolProperties:
    def test_name(self, tool):
        assert tool.name == "file_system"

    def test_description_is_nonempty(self, tool):
        assert len(tool.description) > 0

    def test_parameters_schema(self, tool):
        params = tool.parameters
        assert params["type"] == "object"
        assert "operation" in params["properties"]
        assert params["properties"]["operation"]["enum"] == ["read", "write", "list"]


class TestFileSystemRead:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tool, tmp_path):
        (tmp_path / "hello.txt").write_text("hello world")
        result = await tool.execute(operation="read", path="hello.txt")
        assert result.output == "hello world"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_read_missing_file(self, tool):
        result = await tool.execute(operation="read", path="nope.txt")
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_read_truncates_large_file(self, tool, tmp_path):
        large = "x" * (2 * 1024 * 1024)  # 2MB
        (tmp_path / "big.txt").write_text(large)
        result = await tool.execute(operation="read", path="big.txt")
        assert len(result.output) < len(large)
        assert "truncated" in result.output.lower()

    @pytest.mark.asyncio
    async def test_read_nested_path(self, tool, tmp_path):
        sub = tmp_path / "sub" / "dir"
        sub.mkdir(parents=True)
        (sub / "file.txt").write_text("nested")
        result = await tool.execute(operation="read", path="sub/dir/file.txt")
        assert result.output == "nested"


class TestFileSystemWrite:
    @pytest.mark.asyncio
    async def test_write_creates_file(self, tool, tmp_path):
        result = await tool.execute(operation="write", path="new.txt", content="hello")
        assert result.error is None
        assert (tmp_path / "new.txt").read_text() == "hello"

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tool, tmp_path):
        result = await tool.execute(operation="write", path="a/b/c.txt", content="deep")
        assert result.error is None
        assert (tmp_path / "a" / "b" / "c.txt").read_text() == "deep"

    @pytest.mark.asyncio
    async def test_write_overwrites_existing(self, tool, tmp_path):
        (tmp_path / "exist.txt").write_text("old")
        result = await tool.execute(operation="write", path="exist.txt", content="new")
        assert result.error is None
        assert (tmp_path / "exist.txt").read_text() == "new"


class TestFileSystemList:
    @pytest.mark.asyncio
    async def test_list_directory(self, tool, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "subdir").mkdir()
        result = await tool.execute(operation="list", path=".")
        assert result.error is None
        assert "a.txt" in result.output
        assert "b.txt" in result.output
        assert "subdir" in result.output

    @pytest.mark.asyncio
    async def test_list_missing_directory(self, tool):
        result = await tool.execute(operation="list", path="nope")
        assert result.error is not None


class TestFileSystemSecurity:
    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, tool):
        result = await tool.execute(operation="read", path="../../../etc/passwd")
        assert result.error is not None
        assert "outside workspace" in result.error.lower()

    @pytest.mark.asyncio
    async def test_absolute_path_blocked(self, tool):
        result = await tool.execute(operation="read", path="/etc/passwd")
        assert result.error is not None
        assert "outside workspace" in result.error.lower()

    @pytest.mark.asyncio
    async def test_write_traversal_blocked(self, tool):
        result = await tool.execute(operation="write", path="../escape.txt", content="bad")
        assert result.error is not None
        assert "outside workspace" in result.error.lower()


class TestFileSystemInvalidOperation:
    @pytest.mark.asyncio
    async def test_unknown_operation(self, tool):
        result = await tool.execute(operation="delete", path="file.txt")
        assert result.error is not None
        assert "unknown operation" in result.error.lower()
