# E1-0 atmospheric sound-speed and Doppler uncertainty (planning operator)

**Status:** planning/uncertainty operator implemented and tested; not a validated atmospheric model · 2026-11-05 · **Gate:** [E1-0 instrument feasibility](E1-0-instrument-feasibility.md)

E0 assumes a uniform medium. A real outdoor pass changes the effective sound speed through temperature, humidity, pressure and wind along the propagation path. This operator turns those measured/estimated quantities and their uncertainties into a **predicted Doppler interval** before any residual comparison is made.

## 1. Model

```
c(T, RH) ≈ 331.3 + 0.606·T + 0.0124·RH          (m/s, T in °C, RH in %)
c_eff = c(T, RH) + U_wind · cos θ               (wind component along path)
f_pred = f0 / (1 − v_radial / c_eff)
```

Uncertainty is first order:

```
σ_c = hypot(0.606 σ_T, 0.0124 σ_RH, 0.03 σ_p, |cos θ| σ_U)
σ_f = |f · v / c² / (1 − v/c)| · σ_c
```

The returned interval is the **atmospheric contribution only**; front-end, clock and motion-truth uncertainty are separate terms and must not be silently added as if independent.

## 2. API and tests

`python/phaino_acoustics/atmosphere.py`:

- `Atmosphere(temperature_c, relative_humidity_pct, pressure_hpa, wind_mps, wind_along_path_fraction, uncertainties…)`;
- `sound_speed_mps`, `effective_sound_speed`, `sound_speed_uncertainty`;
- `predicted_doppler_hz`, `doppler_residual_interval_hz`.

Six tests cover reference values, wind projection, uncertainty monotonicity, Doppler interval, supersonic refusal and input validation.

## 3. Honest limits

- The formula is an engineering approximation (≈0.1–0.3 % over ordinary conditions), not a metrological model.
- Wind is a single along-path component, not a profile; terrain and refraction are not modelled.
- The interval is a planning bound; it is not evidence that a real recording matches the model.
- Integrating the operator into the E1 verifier and the read-only cockpit is a next step; E1 collection remains gated.
