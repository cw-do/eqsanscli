from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


def _colorize(name: str, p: Path) -> str:
    if p.is_dir():
        return f"[bold blue]{name}/[/bold blue]"
    s = p.suffix.lower()
    if s in (".py", ".sh"):
        return f"[green]{name}[/green]"
    if s in (".dat", ".txt", ".csv", ".json"):
        return f"[cyan]{name}[/cyan]"
    if s in (".png", ".pdf", ".svg"):
        return f"[magenta]{name}[/magenta]"
    return name


def _format_columns(names: list[str], styled: list[str], width: int = 90) -> str:
    if not names:
        return "[dim](empty)[/dim]"
    max_len = max(len(n) for n in names) + 2
    cols = max(1, width // max_len)
    rows = []
    for i in range(0, len(names), cols):
        parts = []
        for j in range(i, min(i + cols, len(names))):
            pad = max_len - len(names[j])
            parts.append(styled[j] + " " * pad)
        rows.append("".join(parts).rstrip())
    return "\n".join(rows)


async def handle_ls(args: list[str], state: SessionState) -> CommandResult:
    import glob as globmod

    path = args[0] if args else "."
    try:
        if any(c in path for c in ("*", "?", "[")):
            matches = sorted(globmod.glob(path))
            if not matches:
                return CommandResult(success=False, message=f"No matches: {path}")
            names = [str(Path(m)) for m in matches]
            styled = [_colorize(str(Path(m)), Path(m)) for m in matches]
            return CommandResult(success=True, message=_format_columns(names, styled, width=getattr(state, "wrap_width", 90)))

        target = Path(path).expanduser().resolve()
        if not target.exists():
            return CommandResult(success=False, message=f"No such file or directory: {path}")
        if not target.is_dir():
            return CommandResult(success=True, message=str(target))

        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        names = [entry.name + ("/" if entry.is_dir() else "") for entry in entries]
        styled = [_colorize(entry.name, entry) for entry in entries]

        if not names:
            return CommandResult(success=True, message=f"[dim](empty directory)[/dim]")

        return CommandResult(success=True, message=_format_columns(names, styled, width=getattr(state, "wrap_width", 90)))
    except PermissionError:
        return CommandResult(success=False, message=f"Permission denied: {path}")
    except Exception as e:
        return CommandResult(success=False, message=f"Error: {e}")


async def handle_cd(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        path = str(Path.home())
    else:
        path = args[0]
    
    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return CommandResult(success=False, message=f"No such directory: {path}")
        if not target.is_dir():
            return CommandResult(success=False, message=f"Not a directory: {path}")
        
        os.chdir(target)
        return CommandResult(success=True, message=f"[dim]Changed to:[/dim] {target}")
    except PermissionError:
        return CommandResult(success=False, message=f"Permission denied: {path}")
    except Exception as e:
        return CommandResult(success=False, message=f"Error: {e}")


async def handle_pwd(args: list[str], state: SessionState) -> CommandResult:
    return CommandResult(success=True, message=os.getcwd())


async def handle_mkdir(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /mkdir <directory>")
    
    path = args[0]
    try:
        target = Path(path).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        return CommandResult(success=True, message=f"Created: {target.resolve()}")
    except PermissionError:
        return CommandResult(success=False, message=f"Permission denied: {path}")
    except Exception as e:
        return CommandResult(success=False, message=f"Error: {e}")


async def handle_cat(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /cat <file>")
    
    path = args[0]
    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return CommandResult(success=False, message=f"No such file: {path}")
        if target.is_dir():
            return CommandResult(success=False, message=f"Is a directory: {path}")
        
        content = target.read_text()
        if len(content) > 10000:
            content = content[:10000] + f"\n[dim]... (truncated, {len(content)} bytes total)[/dim]"
        return CommandResult(success=True, message=content)
    except PermissionError:
        return CommandResult(success=False, message=f"Permission denied: {path}")
    except UnicodeDecodeError:
        return CommandResult(success=False, message=f"Binary file: {path}")
    except Exception as e:
        return CommandResult(success=False, message=f"Error: {e}")


async def handle_head(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /head <file> [lines]")
    
    path = args[0]
    n_lines = 10
    if len(args) > 1:
        try:
            n_lines = int(args[1])
        except ValueError:
            pass
    
    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return CommandResult(success=False, message=f"No such file: {path}")
        
        with open(target) as f:
            lines = [next(f, None) for _ in range(n_lines)]
            lines = [l for l in lines if l is not None]
        return CommandResult(success=True, message="".join(lines).rstrip())
    except PermissionError:
        return CommandResult(success=False, message=f"Permission denied: {path}")
    except Exception as e:
        return CommandResult(success=False, message=f"Error: {e}")


async def handle_tail(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /tail <file> [lines]")
    
    path = args[0]
    n_lines = 10
    if len(args) > 1:
        try:
            n_lines = int(args[1])
        except ValueError:
            pass
    
    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return CommandResult(success=False, message=f"No such file: {path}")
        
        with open(target) as f:
            all_lines = f.readlines()
        lines = all_lines[-n_lines:] if len(all_lines) > n_lines else all_lines
        return CommandResult(success=True, message="".join(lines).rstrip())
    except PermissionError:
        return CommandResult(success=False, message=f"Permission denied: {path}")
    except Exception as e:
        return CommandResult(success=False, message=f"Error: {e}")


async def handle_cp(args: list[str], state: SessionState) -> CommandResult:
    if len(args) < 2:
        return CommandResult(success=False, message="Usage: /cp <source> <destination>")
    
    src, dst = args[0], args[1]
    try:
        import shutil
        src_path = Path(src).expanduser().resolve()
        dst_path = Path(dst).expanduser()
        
        if not src_path.exists():
            return CommandResult(success=False, message=f"No such file: {src}")
        
        if src_path.is_dir():
            shutil.copytree(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)
        return CommandResult(success=True, message=f"Copied: {src} → {dst_path.resolve()}")
    except Exception as e:
        return CommandResult(success=False, message=f"Error: {e}")


async def handle_mv(args: list[str], state: SessionState) -> CommandResult:
    if len(args) < 2:
        return CommandResult(success=False, message="Usage: /mv <source> <destination>")
    
    src, dst = args[0], args[1]
    try:
        import shutil
        src_path = Path(src).expanduser().resolve()
        dst_path = Path(dst).expanduser()
        
        if not src_path.exists():
            return CommandResult(success=False, message=f"No such file: {src}")
        
        shutil.move(str(src_path), str(dst_path))
        return CommandResult(success=True, message=f"Moved: {src} → {dst_path.resolve()}")
    except Exception as e:
        return CommandResult(success=False, message=f"Error: {e}")


async def handle_rm(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /rm <file> [file2 ...]")
    
    results = []
    for path in args:
        try:
            target = Path(path).expanduser().resolve()
            if not target.exists():
                results.append(f"[red]✗[/red] No such file: {path}")
                continue
            if target.is_dir():
                import shutil
                shutil.rmtree(target)
            else:
                target.unlink()
            results.append(f"[green]✓[/green] Removed: {path}")
        except Exception as e:
            results.append(f"[red]✗[/red] {path}: {e}")
    
    return CommandResult(success=True, message="\n".join(results))


async def handle_shell(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /sh <command>")
    
    cmd = " ".join(args)
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout + result.stderr
        if not output.strip():
            output = "[dim](no output)[/dim]"
        if result.returncode != 0:
            return CommandResult(success=False, message=f"[red]Exit code: {result.returncode}[/red]\n{output}")
        return CommandResult(success=True, message=output.rstrip())
    except subprocess.TimeoutExpired:
        return CommandResult(success=False, message="Command timed out (30s limit)")
    except Exception as e:
        return CommandResult(success=False, message=f"Error: {e}")
