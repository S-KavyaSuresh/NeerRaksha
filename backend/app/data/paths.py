from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / "data"

CSV_FILES = {
    "dams": DATA_ROOT / "dams" / "India_All_Dams_Dataset_700_Records.csv",
    "breach": DATA_ROOT / "breach" / "India_Dam_Breach_Scenarios_700.csv",
    "reservoir": DATA_ROOT / "reservoirs" / "India_Reservoir_Level_Storage_Geometry_700.csv",
    "river_geometry": DATA_ROOT / "rivers" / "India_River_Geometry_CrossSections_700.csv",
    "river_discharge": DATA_ROOT / "rivers" / "India_River_Discharge_WaterLevel_700.csv",
    "roughness": DATA_ROOT / "roughness" / "India_LULC_Surface_Roughness_700.csv",
    "weather": DATA_ROOT / "weather" / "India_Rainfall_Weather_700.csv",
    "population": DATA_ROOT / "exposure" / "India_Population_Settlement_Exposure_700.csv",
    "assets": DATA_ROOT / "exposure" / "India_Roads_Buildings_Exposed_Assets_700.csv",
}
DEM_ROOT = DATA_ROOT / "dem"


def discover_dem_files() -> list[Path]:
    return sorted(DEM_ROOT.rglob("*.tif")) if DEM_ROOT.exists() else []
