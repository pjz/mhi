let
  # pinned for python38 + native libs (kept as-is; this old pin's own `uv`
  # package is too outdated to support `uv sync`/`uv lock`/`uv publish`)
  pkgs = import (fetchTarball https://github.com/NixOS/nixpkgs/archive/336eda0d07dc5e2be1f923990ad9fdb6bc8e28e3.tar.gz) {};
  # newer pin, just for up-to-date dev tooling
  toolPkgs = import (fetchTarball https://github.com/NixOS/nixpkgs/archive/nixos-25.05.tar.gz) {};
in

pkgs.mkShell {
  buildInputs = [
    pkgs.python38
    #pkgs.python38Packages.pylibmc
    pkgs.libmemcached
    pkgs.rdkafka
    pkgs.zlib
    pkgs.cmake
    pkgs.rabbitmq-c
    toolPkgs.uv
    toolPkgs.go-task
  ];
}
