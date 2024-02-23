from fastapi import FastAPI
from sim import SimulationManager
import json
from hunters import Hunter, Borge, Ozzy

from pydantic import BaseModel, create_model


def start_application():
    app = FastAPI(title="HunterSIM", version="1.0.0")
    return app


app = start_application()


class ApiModel(BaseModel):
    meta: dict
    stats: dict
    talents: dict
    attributes: dict
    inscryptions: dict
    mods: dict
    relics: dict
    gems: dict

    def __getitem__(self, item):
        return getattr(self, item)


borgeDummy = Borge.load_dummy()


class BorgeAPI(ApiModel):
    meta: dict = borgeDummy["meta"]
    stats: dict = borgeDummy["stats"]
    talents: dict = borgeDummy["talents"]
    attributes: dict = borgeDummy["attributes"]
    inscryptions: dict = borgeDummy["inscryptions"]
    mods: dict = borgeDummy["mods"]
    relics: dict = borgeDummy["relics"]
    gems: dict = borgeDummy["gems"]


ozzyDummy = Ozzy.load_dummy()


class OzzyAPI(ApiModel):
    meta: dict = ozzyDummy["meta"]
    stats: dict = ozzyDummy["stats"]
    talents: dict = ozzyDummy["talents"]
    attributes: dict = ozzyDummy["attributes"]
    inscryptions: dict = ozzyDummy["inscryptions"]
    mods: dict = ozzyDummy["mods"]
    relics: dict = ozzyDummy["relics"]
    gems: dict = ozzyDummy["gems"]


@app.get("/health")
async def healthz():
    return {"status": "running"}


@app.post("/run")
async def run_sim(config: OzzyAPI | BorgeAPI, iterations: int = 50):
    smgr = SimulationManager(hunter_config_dict=config.model_dump())
    data = smgr.api_run(iterations, num_processes=-1)
    return data


@app.post("/compare")
async def run_compare(
    first_config: OzzyAPI | BorgeAPI,
    second_config: OzzyAPI | BorgeAPI,
    iterations: int = 50,
):
    smgr = SimulationManager(hunter_config_dict=first_config.model_dump())
    data = smgr.api_compare_against(
        second_config.model_dump(), iterations, num_processes=-1
    )
    return data
