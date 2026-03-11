from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


async def handle_ls(args: list[str], state: SessionState) -> CommandResult:
    path = args[0] if args else "."
    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return CommandResult(success=False, message=f"No such file or directory: {path}")
        if not target.is_dir():
            return CommandResult(success=True, message=str(target))
        
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = []
        for entry in entries:
            if entry.is_dir():
                lines.append(f"[bold blue]{entry.name}/[/bold blue]")
            elif entry.suffix in (".py", ".sh"):
                lines.append(f"[green]{entry.name}[/green]")
            elif entry.suffix in (".dat", ".txt", ".csv", ".json"):
                lines.append(f"[cyan]{entry.name}[/cyan]")
            else:
                lines.append(entry.name)
        
        if not lines:
            return CommandResult(success=True, message=f"[dim](empty directory)[/dim]")
        
        output = "  ".join(lines)
        return CommandResult(success=True, message=output)
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
