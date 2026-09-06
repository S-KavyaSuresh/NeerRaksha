from uuid import UUID

DAM_ID = UUID("11111111-1111-4111-8111-111111111111")
PARTIAL_ID = UUID("22222222-2222-4222-8222-222222222222")
MAJOR_ID = UUID("33333333-3333-4333-8333-333333333333")
SIMULATION_ID = UUID("44444444-4444-4444-8444-444444444444")
SUMMARY_ID = UUID("55555555-5555-4555-8555-555555555555")
TIMELINE = [
    {"minute": 0, "depth_m": 0, "flooded_area_km2": 0},
    {"minute": 15, "depth_m": 2.1, "flooded_area_km2": 9.6},
    {"minute": 30, "depth_m": 5.3, "flooded_area_km2": 24.2},
    {"minute": 60, "depth_m": 8.4, "flooded_area_km2": 42.8},
]
