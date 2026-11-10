"""Non-blocking ICMP ping using the operating system's ping executable."""

import asyncio
import math
import platform
import subprocess
from ipaddress import ip_address

from loguru import logger

from db.models import Node


def _ping_in_thread(arguments: list[str], timeout: float) -> bool:
    """Windows reload servers can use a loop without async subprocess support."""
    try:
        result = subprocess.run(
            arguments,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 1,
            check=False,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except OSError:
        logger.exception("Cannot launch ping; ensure the ping executable is installed")
        return False


async def ping(node: Node | str, timeout: float = 5.0) -> bool:
    target = node.ip if isinstance(node, Node) else node
    try:
        address = str(ip_address(target))
    except ValueError:
        logger.warning("Cannot ping invalid IP address: {}", target)
        return False

    if platform.system() == "Windows":
        arguments = ["ping", "-n", "1", "-w", str(math.ceil(timeout * 1000)), address]
    else:
        arguments = ["ping", "-n", "-c", "1", "-W", str(math.ceil(timeout)), address]

    try:
        process = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except NotImplementedError:
        return await asyncio.to_thread(_ping_in_thread, arguments, timeout)
    except OSError:
        logger.exception("Cannot launch ping; ensure the ping executable is installed")
        return False

    try:
        return await asyncio.wait_for(process.wait(), timeout=timeout + 1) == 0
    except TimeoutError:
        logger.debug("Ping timed out for {}", address)
        return False
    finally:
        # Also reap the child if the scheduler cancels this task during shutdown.
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
