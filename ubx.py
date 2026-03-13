import ast
import asyncio
import glob
import json
import logging
import os
from pathlib import Path

import aiofiles
from app import BOT, Message, bot


class CodebaseIndexer(ast.NodeVisitor):
    def __init__(self, source_code: str, module_name: str):
        self.source_code = source_code
        self.module_name = module_name
        self.records = []
        self.current_class = None

    def _get_source_segment(self, node):
        try:
            return ast.get_source_segment(self.source_code, node)
        except Exception:
            return None

    def visit_Import(self, node):
        for alias in node.names:
            self.records.append({
                "type": "import",
                "name": alias.name,
                "module": self.module_name,
                "start_line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno)
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
            self.records.append({
                "type": "import_from",
                "name": alias.name,
                "from_module": module,
                "module": self.module_name,
                "start_line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno)
            })
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        docstring = ast.get_docstring(node)
        bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
        
        class_record = {
            "type": "class",
            "name": node.name,
            "module": self.module_name,
            "bases": bases,
            "docstring": docstring,
            "start_line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "source": self._get_source_segment(node)
        }
        self.records.append(class_record)
        
        # Keep track of the current class context for methods
        prev_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node):
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node):
        self._handle_function(node, is_async=True)

    def _handle_function(self, node, is_async):
        docstring = ast.get_docstring(node)
        args = [arg.arg for arg in node.args.args]
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")

        record_type = "method" if self.current_class else "function"
        
        func_record = {
            "type": record_type,
            "name": node.name,
            "module": self.module_name,
            "class_name": self.current_class,  # None if it's a generic function
            "is_async": is_async,
            "arguments": args,
            "docstring": docstring,
            "start_line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "source": self._get_source_segment(node)
        }
        self.records.append(func_record)
        self.generic_visit(node)


def parse_python_file(file_path: Path, root_dir: Path) -> list:
    """Parse a single python file and return its semantic records."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            source_code = f.read()
    except Exception as e:
        logging.error(f"Failed to read {file_path}: {e}")
        return []

    try:
        tree = ast.parse(source_code, filename=str(file_path))
    except SyntaxError as e:
        logging.warning(f"Syntax error skipping AST parse for {file_path}: {e}")
        return []
    except Exception as e:
        logging.error(f"AST parse error for {file_path}: {e}")
        return []

    # Derive module name from relative path
    rel_path = file_path.relative_to(root_dir) if file_path.is_relative_to(root_dir) else file_path
    module_name = str(rel_path).replace(os.sep, ".").replace(".py", "")

    indexer = CodebaseIndexer(source_code, module_name)
    indexer.visit(tree)
    
    # Also add a file-level record 
    file_record = {
        "type": "module",
        "name": module_name,
        "path": str(rel_path),
        "docstring": ast.get_docstring(tree)
    }
    
    return [file_record] + indexer.records


@bot.add_cmd(cmd="ubx")
async def semantic_index_codebase(bot: BOT, message: Message):
    """
    CMD: UBX
    INFO: Build a machine-readable semantic JSON index of the codebase via AST mapping.
    FLAGS: -u to upload the index file to chat
    USAGE: ,ubx | ,ubx -u
    """
    CONTEXT_FILE = "codebase_index.json"
    status = await message.reply("<code>Building semantic index via AST...</code>")
    
    try:
        root_dir = Path(os.getcwd())
        scan_dirs = ["app/"]

        try:
            import ub_core
            if hasattr(ub_core, "ub_core_dirname"):
                ub_core_path = ub_core.ub_core_dirname
                if os.path.exists(ub_core_path):
                    scan_dirs.append(ub_core_path)
                else:
                    scan_dirs.append("ub_core/")
            else:
                scan_dirs.append("ub_core/")
        except ImportError:
            scan_dirs.append("ub_core/")
        
        scan_dirs.append("plugins/") # Adding plugins directory to index as well.

        all_files = []
        for directory in scan_dirs:
            dir_path = directory if os.path.isabs(directory) else os.path.join(root_dir, directory)
            all_files.extend(glob.glob(f"{dir_path}/**/*.py", recursive=True))

        final_files = sorted([Path(f) for f in all_files], key=lambda p: str(p).lower())
        
        # Parse all files (Runs synchronously as ast is CPU bound, but it's fast enough)
        # To avoid blocking the event loop for too long on massive codebases, we run it in executor
        loop = asyncio.get_running_loop()
        
        all_records = []
        for file_path in final_files:
            # We skip generating AST for the index file itself if it accidentally was named .py
            if file_path.name == CONTEXT_FILE:
                continue
            
            records = await loop.run_in_executor(None, parse_python_file, file_path, root_dir)
            all_records.extend(records)

        index_data = {
            "metadata": {
                "total_files_indexed": len(final_files),
                "total_records": len(all_records)
            },
            "records": all_records
        }

        # Write the JSON output
        async with aiofiles.open(CONTEXT_FILE, "w", encoding="utf-8") as f:
            await f.write(json.dumps(index_data, indent=2))

        caption = f"Semantic index generated.\nIndexed Files: {len(final_files)}\nAST Records: {len(all_records)}"

        if "-u" in message.flags:
            await message.reply_document(document=CONTEXT_FILE, caption=caption)
            await status.delete()
        else:
            await status.edit(caption)

    except Exception as e:
        await status.edit(f"Indexing failed: {e}")
