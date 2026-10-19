# LLM Inference Platform

A minimal Linux command-line tool that renders Kubernetes JSON for a vLLM-compatible container. It creates a `Deployment` with NVIDIA GPU requests and limits, CPU and memory bounds, health probes, and a matching internal `ClusterIP` `Service`.

## Prerequisites

- Linux with Python 3.9 or newer
- A Kubernetes cluster with GPU worker nodes
- NVIDIA drivers and the NVIDIA Kubernetes device plugin installed and working
- A vLLM-compatible container image you trust
- Enough GPU memory, system memory, and storage for the selected model
- `kubectl` only if you intend to apply the rendered JSON

GPU discovery and scheduling depend on the NVIDIA device plugin exposing the `nvidia.com/gpu` resource. This tool does not install drivers, the plugin, a container runtime, model storage, ingress, autoscaling, or monitoring.

## Run from the repository

Render the default one-GPU configuration:

```bash
python3 -m llm_inference_platform render \
  --image ghcr.io/example/your-vllm-image:tag \
  --model your-org/your-model > manifest.json
```

Choose explicit resource bounds and two GPUs:

```bash
python3 -m llm_inference_platform render \
  --name text-generation \
  --namespace inference \
  --image ghcr.io/example/your-vllm-image:tag \
  --model your-org/your-model \
  --gpu-count 2 \
  --cpu-request 4 \
  --cpu-limit 8 \
  --memory-request 32Gi \
  --memory-limit 64Gi > manifest.json
```

The command only prints JSON. It does not connect to a cluster or apply anything. After reviewing the file, you can apply it yourself with:

```bash
kubectl apply -f manifest.json
```

The service is internal to the cluster. A workload in the same namespace can call the OpenAI-compatible endpoint at `http://text-generation:8000/v1` when using the example name above.

## Hugging Face token

Create the secret separately from a protected file populated by your approved secret-management workflow. Replace the example path with that file's path; the file should contain only the token. Do not commit it or put the token itself in shell arguments:

```bash
kubectl -n inference create secret generic hugging-face \
  --from-file=token=/secure/path/hugging-face-token
```

Reference that existing secret when rendering:

```bash
python3 -m llm_inference_platform render \
  --image ghcr.io/example/your-vllm-image:tag \
  --model your-org/your-model \
  --namespace inference \
  --hf-secret hugging-face > manifest.json
```

The generated Deployment uses a Kubernetes `secretKeyRef`; it never includes the secret value. Change the key name with `--hf-secret-key` if your Secret does not use `token`.

## Cost estimate

Supply the hourly price from your GPU provider, the planned hours, and the GPU count:

```bash
python3 -m llm_inference_platform cost \
  --hourly-gpu-price 1.25 \
  --hours 24 \
  --gpu-count 2
```

This is simple arithmetic: hourly GPU price × hours × GPU count. The estimate excludes CPU/RAM compute, storage, network, taxes, and all other overhead. It does not fetch live pricing.

## Design decisions

- **Generate manifests without deploying.** Rendering keeps cluster access separate and lets operators review resource settings before rollout.
- **Explicit GPU requests.** GPU count is a scheduling input, not proof that a model fits in memory. Model sizing and multi-GPU runtime arguments require workload-specific decisions.
- **User-supplied pricing.** A transparent calculation avoids implying live billing integration. Provider pricing APIs and measured utilization would be needed for operational cost reporting.
- **Internal service by default.** External access requires a separate decision about authentication, TLS, and network exposure.

For production use, prioritize model startup behavior, capacity measurement, a persistent model cache, and metrics collected from the actual serving stack.

## Status and limitations

- Initial implementation; no local tests, benchmarks, or production validation have been performed. Review generated manifests for your model, image, and cluster.

- The default `/health` probes assume the supplied image exposes vLLM's health endpoint on port 8000.
- Model startup can take longer than the probe defaults. Adjust the generated JSON for large or cold-starting models.
- Multiple GPUs may require extra vLLM arguments such as tensor parallel size. Add image-specific arguments after rendering if needed.
- Requests and limits are configuration inputs, not capacity checks. Kubernetes can leave the Pod pending when suitable nodes are unavailable.
- Private image registries, persistent model caches, TLS, authentication, ingress, disruption budgets, autoscaling, and observability are outside this repository's scope.

## License

MIT © Juan M De Sousa
