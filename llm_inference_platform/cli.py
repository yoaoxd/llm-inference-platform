"""Command-line interface for rendering vLLM Kubernetes resources."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any, Sequence


DNS_LABEL = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def nonnegative_float(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def kubernetes_name(value: str) -> str:
    if len(value) > 63 or not DNS_LABEL.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "must be a lowercase Kubernetes DNS label (maximum 63 characters)"
        )
    return value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="llm-inference-platform",
        description="Render Kubernetes JSON for a GPU-backed vLLM service.",
    )
    subcommands = root.add_subparsers(dest="command")

    render = subcommands.add_parser("render", help="render a Deployment and Service")
    render.add_argument("--name", type=kubernetes_name, default="vllm")
    render.add_argument("--namespace", type=kubernetes_name, default="default")
    render.add_argument("--image", required=True, help="vLLM-compatible container image")
    render.add_argument("--model", required=True, help="model identifier or mounted path")
    render.add_argument("--replicas", type=positive_int, default=1)
    render.add_argument("--port", type=positive_int, default=8000)
    render.add_argument("--gpu-count", type=positive_int, default=1)
    render.add_argument("--cpu-request", default="2")
    render.add_argument("--cpu-limit", default="4")
    render.add_argument("--memory-request", default="8Gi")
    render.add_argument("--memory-limit", default="16Gi")
    render.add_argument(
        "--hf-secret",
        help="existing Secret containing a Hugging Face token; never rendered inline",
    )
    render.add_argument("--hf-secret-key", default="token")

    cost = subcommands.add_parser("cost", help="estimate GPU rental cost")
    cost.add_argument("--hourly-gpu-price", type=nonnegative_float, required=True)
    cost.add_argument("--hours", type=nonnegative_float, required=True)
    cost.add_argument("--gpu-count", type=positive_int, default=1)
    return root


def manifests(args: argparse.Namespace) -> dict[str, Any]:
    labels = {"app.kubernetes.io/name": args.name}
    resources = {
        "requests": {
            "cpu": args.cpu_request,
            "memory": args.memory_request,
            "nvidia.com/gpu": str(args.gpu_count),
        },
        "limits": {
            "cpu": args.cpu_limit,
            "memory": args.memory_limit,
            "nvidia.com/gpu": str(args.gpu_count),
        },
    }
    container: dict[str, Any] = {
        "name": "vllm",
        "image": args.image,
        "args": ["--model", args.model, "--host", "0.0.0.0", "--port", str(args.port)],
        "ports": [{"name": "http", "containerPort": args.port}],
        "resources": resources,
        "readinessProbe": {
            "httpGet": {"path": "/health", "port": "http"},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
            "failureThreshold": 12,
        },
        "livenessProbe": {
            "httpGet": {"path": "/health", "port": "http"},
            "initialDelaySeconds": 60,
            "periodSeconds": 20,
            "failureThreshold": 3,
        },
    }
    if args.hf_secret:
        container["env"] = [
            {
                "name": "HF_TOKEN",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": args.hf_secret,
                        "key": args.hf_secret_key,
                    }
                },
            }
        ]

    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": args.name, "namespace": args.namespace},
        "spec": {
            "replicas": args.replicas,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": {"containers": [container]},
            },
        },
    }
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": args.name, "namespace": args.namespace},
        "spec": {
            "type": "ClusterIP",
            "selector": labels,
            "ports": [{"name": "http", "port": args.port, "targetPort": "http"}],
        },
    }
    return {"apiVersion": "v1", "kind": "List", "items": [deployment, service]}


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.command is None:
        parser().print_help()
        return
    if args.command == "cost":
        estimate = args.hourly_gpu_price * args.hours * args.gpu_count
        print(
            json.dumps(
                {
                    "estimated_gpu_cost": round(estimate, 2),
                    "currency": "USD",
                    "hourly_gpu_price": args.hourly_gpu_price,
                    "hours": args.hours,
                    "gpu_count": args.gpu_count,
                    "note": "Estimate excludes CPU/RAM compute, storage, network, taxes, and other overhead.",
                },
                indent=2,
            )
        )
        return
    print(json.dumps(manifests(args), indent=2))
