"""Backward-compatible entrypoint — use server.soft_shim. """
from server.soft_shim import main

if __name__ == "__main__":
    main()
