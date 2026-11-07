# Third-party components and licences

The public snapshot does not vendor these dependencies. The reproduction environment uses:

| Component | Version | Licence | Role |
|---|---|---|---|
| NumPy | 2.4.4 | BSD-3-Clause (with bundled-component notices in its metadata) | numerical arrays |
| SciPy | 1.17.1 | BSD-3-Clause; binary wheels may bundle OpenBLAS/LAPACK/GCC runtime under their own notices | numerical routines |
| SymPy | 1.14.0 | BSD | symbolic checks |
| pytest | dev dependency | MIT | test runner |
| Docker base image | `rust:1.94-slim` digest in `containers/repro/Dockerfile` | base-image terms; image layers not included in this snapshot | reproducibility harness |

## Notes

- The candidate snapshot does not redistribute NumPy, SciPy, SymPy, pytest, or container image layers. Users install them under their own terms.
- SciPy binary wheels may include OpenBLAS/LAPACK and GCC runtime libraries with separate notices. A user who redistributes a built environment is responsible for those notices.
- `NOTICE` retains the project attribution. It is not a complete dependency notice bundle.
- No third-party papers, figures, datasets, raw audio, screenshots, or code were copied into the snapshot. Documents cite external work by reference only.
