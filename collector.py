"""
Collect host states and container states based on nvitop and docker (Docker's offcial Python SDK).
"""
import os.path as osp
from datetime import datetime
import socket
from typing import List, Union, Dict, Literal, Tuple
from concurrent import futures as f
from pprint import pprint

# https://github.com/XuehaiPan/nvitop
# pip install nvitop
from nvitop import host, Device

# Docker SDK for Python
# https://docker-py.readthedocs.io/en/stable/index.html
# pip install docker
import docker


class StatsCollector:
    UNIT_CONVERSION = {
        "B2M": {"div": 1 << 20, "unit": "M"},
        "B2G": {"div": 1 << 30, "unit": "G"},
        "B2T": {"div": 1 << 40, "unit": "T"},
    }

    def __init__(self):
        if osp.exists("/var/run/docker.sock"):
            self.docker_client = docker.from_env()
        else:
            try:
                self.docker_client = docker.DockerClient(base_url="tcp://127.0.0.1:2375")
            except ConnectionRefusedError:
                raise RuntimeError("Connection to 127.0.0.1:2375 is refused, please check your docker configuration, exiting...")

        # Store info that is constant
        self._hostname = self._get_hostname()
        self._ip = self._get_ip_addr()

    def __del__(self):
        if hasattr(self, "docker_client"):
            self.docker_client.close()

    @staticmethod
    def _convert_unit(
        value: float,
        convert_type: Literal = "B2G",
        n_digits: int = 1,
        append_unit: bool = True,
    ) -> Union[str, float]:
        """
        Convert values in bytes into M / G / T.
        """
        if convert_type not in StatsCollector.UNIT_CONVERSION:
            return ValueError(
                f"Unknown convert type: {convert_type}, "
                f"select from {StatsCollector.UNIT_CONVERSION.keys()}"
            )

        converted_value = round(
            value / StatsCollector.UNIT_CONVERSION[convert_type]["div"], n_digits
        )
        if append_unit:
            return (
                str(converted_value)
                + StatsCollector.UNIT_CONVERSION[convert_type]["unit"]
            )
        else:
            return converted_value

    @staticmethod
    def _perc_str_to_float(perc_str: str) -> float:
        if perc_str.endswith('%'):
            return float(perc_str[:-1])
        return float(perc_str)

    @staticmethod
    def _get_hostname() -> str:
        return socket.gethostname()

    @staticmethod
    def _get_ip_addr() -> str:
        st = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            st.connect(("10.255.255.255", 1))
            ip = st.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            st.close()
        return ip

    @staticmethod
    def _get_cpu_percent() -> float:
        return host.cpu_percent()

    @staticmethod
    def _get_host_memory() -> Dict[str, Union[float, str]]:
        mem = host.virtual_memory()
        return {
            "perc-used": mem.percent,
            "used/total": f"{StatsCollector._convert_unit(mem.used)} / {StatsCollector._convert_unit(mem.total)}",
        }

    @staticmethod
    def _get_gpu_stats() -> List[Dict[str, Union[float, str]]]:
        gpu_stats = []
        for device in Device.all():
            gpu_stats.append(
                {
                    "id": device.index,
                    "model": device.name(),
                    "mem-perc-used": device.memory_percent(),
                    "mem-used/total": f"{StatsCollector._convert_unit(device.memory_used())} / "
                    f"{StatsCollector._convert_unit(device.memory_total())}",
                    "util-perc": device.gpu_utilization(),
                }
            )
        return gpu_stats

    @staticmethod
    def _get_gpu_process_stats() -> List[Dict[str, Union[int, float, str]]]:
        gpu_process_stats = []
        for device in Device.all():
            processes = device.processes()
            if len(processes) > 0:
                for pid, process in processes.items():
                    gpu_process_stats.append(
                        {
                            "pid": pid,
                            "gpu-idx": process.device.index,
                            "mem-perc-used": process.gpu_memory_percent(),
                            "mem-used": StatsCollector._convert_unit(
                                process.gpu_memory()
                            ),
                            "sm-util": process.gpu_sm_utilization(),
                        }
                    )

        return gpu_process_stats

    @staticmethod
    def _parse_container_basic_stats(container) -> Tuple[str, Dict]:
        # docker stats API is slow, especially when there are multiple containers. See: 
        # - https://github.com/moby/moby/issues/23188
        # - https://stackoverflow.com/questions/68675259/a-problem-on-getting-docker-stats-by-python
        stats = container.stats(stream=False)

        # Ref: https://github.com/moby/moby/blob/eb131c5383db8cac633919f82abad86c99bffbe5/cli/command/container/stats_helpers.go#L175-L188
        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]

        return container.short_id, {
            "name": stats["name"][1:] if stats["name"].startswith('/') else stats["name"],
            "cpu-perc": round((cpu_delta / system_delta) * stats["cpu_stats"]["online_cpus"] * 100, 1),
            "mem": {
                "perc-used": round(stats["memory_stats"]["usage"] / stats["memory_stats"]["limit"] * 100, 1),
                "used/total": f"{StatsCollector._convert_unit(stats['memory_stats']['usage'])} / "
                            f"{StatsCollector._convert_unit(stats['memory_stats']['limit'])}"
            }
        }

    def _get_container_basic_stats(self) -> Dict[str, Dict]:
        """
        There are 2 known ways to obtain CPU, memory and other basic stats of docker containers:
        1. Call "docker stats" command on host
        2. Docker Python SDK. `Container` objects have a method called `stats`.
            https://docker-py.readthedocs.io/en/stable/containers.html#docker.models.containers.Container.stats
        The 1st way returns more concise information, while 2nd way returns more detailed infomation.

        Through rough tests, the speeds of the two ways are very close. To avoid access docker command, 2nd way is adopted here.
        """
        container_basic_stats = {}
        with f.ThreadPoolExecutor() as executor:
            futures = []
            for container in self.docker_client.containers.list():
                futures.append(executor.submit(StatsCollector._parse_container_basic_stats, container))

            for future in f.as_completed(futures):
                short_id, stats = future.result()
                container_basic_stats[short_id] = stats

        return container_basic_stats

    @staticmethod
    def _determine_pid_which_container(pid: int, containers: List) -> Union[str, None]:
        """
        Determine the given pid belongs to which container.
        Return the short id or None.
        """
        pid = str(pid)
        for container in containers:
            for process_info in container.top()["Processes"]:
                if process_info[1] == pid:  # 2nd item represents PID
                    return container.short_id
        return None

    def _get_full_container_stats(self) -> Dict:
        """
        Aggregate GPU stats into container basic stats.
        """
        container_stats = self._get_container_basic_stats()

        # Create an empty sub-dict for GPU process(es)
        for container_stat in container_stats.values():
            container_stat["gpu-proc"] = []

        containers = self.docker_client.containers.list()
        for gpu_proc in StatsCollector._get_gpu_process_stats():
            container_id = StatsCollector._determine_pid_which_container(
                gpu_proc["pid"], containers
            )

            if container_id is not None:
                container_gpu_proc = container_stats[container_id]["gpu-proc"]
                container_gpu_proc.append({
                    "pid": gpu_proc["pid"],
                    "gpu-idx": gpu_proc["gpu-idx"],
                    "mem-perc-used": gpu_proc["mem-perc-used"],
                    "sm-util": gpu_proc["sm-util"],
                })

        return container_stats

    def get_stats(self) -> Dict:
        """
        Assemble into the final complete structure.
        """
        return {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": self._hostname,
            "ip": self._ip,
            "host-stats": {
                "cpu-perc": self._get_cpu_percent(),
                "mem": self._get_host_memory(),
                "gpu": self._get_gpu_stats()
            },
            "container-stats": self._get_full_container_stats(),
            "note": '',
        }


if __name__ == "__main__":
    collector = StatsCollector()
    pprint(collector.get_stats())
