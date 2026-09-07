from .ujjani_solver import run
if __name__ == "__main__":
    summary = run(); print(f"Ujjani approximate prototype complete: {summary['runtime_seconds']:.1f}s, area {summary['flooded_area_km2']:.2f} km²")
