import requests
import os
import tarfile
import json
import hashlib
import argparse
import sys


def get_auth_token(repo):
    auth_url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
    response = requests.get(auth_url)
    return response.json()['token']


def download_docker_image(image, tag, save_path=None, architecture="amd64"):
    if '/' not in image:
        repo = f"library/{image}"
    else:
        repo = image

    token = get_auth_token(repo)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json"
    }

    manifest_url = f"https://registry-1.docker.io/v2/{repo}/manifests/{tag}"

    response = requests.get(manifest_url, headers=headers)
    if response.status_code != 200:
        print(f"Error getting manifest: {response.status_code}")
        print(response.text)
        return

    content_type = response.headers.get('Content-Type')
    if content_type in ['application/vnd.docker.distribution.manifest.list.v2+json',
                        'application/vnd.oci.image.index.v1+json']:
        print("Multi-architecture image detected. Selecting appropriate manifest...")
        manifest_list = response.json()
        for m in manifest_list.get("manifests", []):
            if m.get("platform", {}).get("architecture") == architecture and m.get("platform", {}).get("os") == "linux":
                manifest_digest = m["digest"]
                break
        else:
            print(f"No manifest found for architecture: {architecture}")
            return

        manifest_url = f"https://registry-1.docker.io/v2/{repo}/manifests/{manifest_digest}"
        headers[
            "Accept"] = "application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json"
        response = requests.get(manifest_url, headers=headers)
        if response.status_code != 200:
            print(f"Error getting manifest for architecture {architecture}: {response.status_code}")
            print(response.text)
            return
        manifest = response.json()
    else:
        manifest = response.json()

    if "layers" not in manifest:
        print("Error: Unexpected manifest structure")
        print(json.dumps(manifest, indent=2))
        return

    if "config" in manifest:
        config_digest = manifest["config"]["digest"]
        config_url = f"https://registry-1.docker.io/v2/{repo}/blobs/{config_digest}"
        config_response = requests.get(config_url, headers=headers)
        config = config_response.json()
    else:
        print("Warning: No config found in manifest. Using empty config.")
        config = {}

    total_size = sum(layer['size'] for layer in manifest['layers'])
    print(f"Total uncompressed size of all layers: {total_size / 1024 / 1024:.2f} MB")

    if save_path is None:
        save_path = f"{image.split('/')[-1]}_{tag}.tar"

    with tarfile.open(save_path, "w") as tar:
        if "config" in manifest:
            config_file = f"{config_digest[7:]}.json"
            with open(config_file, "w") as f:
                json.dump(config, f)
            tar.add(config_file)
            os.remove(config_file)
        else:
            config_file = "config.json"
            with open(config_file, "w") as f:
                json.dump({}, f)
            tar.add(config_file)
            os.remove(config_file)

        for i, layer in enumerate(manifest["layers"]):
            layer_digest = layer["digest"]
            layer_url = f"https://registry-1.docker.io/v2/{repo}/blobs/{layer_digest}"
            layer_response = requests.get(layer_url, headers=headers, stream=True)
            layer_file = f"layer_{i}.tar.gz"
            with open(layer_file, "wb") as f:
                for chunk in layer_response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Verify layer integrity
            with open(layer_file, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
                if f"sha256:{file_hash}" != layer_digest:
                    print(f"Warning: Layer {i} hash mismatch!")
                else:
                    print(f"Layer {i} verified successfully.")

            tar.add(layer_file)
            os.remove(layer_file)

        manifest_json = [{
            "Config": config_file,
            "RepoTags": [f"{image}:{tag}"],
            "Layers": [f"layer_{i}.tar.gz" for i in range(len(manifest["layers"]))]
        }]
        with open("manifest.json", "w") as f:
            json.dump(manifest_json, f)
        tar.add("manifest.json")
        os.remove("manifest.json")

    print(f"{image}:{tag} image ({architecture}) downloaded and saved as {save_path}")
    print(f"Compressed tar size: {os.path.getsize(save_path) / 1024 / 1024:.2f} MB")
    print(f"Load the image using: docker load -i {save_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Docker images")
    parser.add_argument("image", help="Docker image to download (e.g., 'ubuntu:20.04' or 'nginx:latest')")
    parser.add_argument("-o", "--output", help="Output file name (default: <image>_<tag>.tar)")
    parser.add_argument("-a", "--arch", default="amd64", help="Architecture (default: amd64)")
    args = parser.parse_args()

    try:
        image, tag = args.image.split(":", 1)
    except ValueError:
        print("Error: Image should be in the format 'name:tag'")
        sys.exit(1)

    download_docker_image(image, tag, args.output, args.arch)