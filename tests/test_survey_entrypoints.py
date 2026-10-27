from surmap.rpc.description import ServerDescription
from surmap.survey.cm5_main import build_description as build_cm5_description
from surmap.survey.station_main import build_description as build_station_description


def test_the_cm5_entrypoint_serves_the_survey_service_and_health() -> None:
    # When the CM5 process builds its server description
    description = build_cm5_description()

    # Then it mounts the survey service and a health route
    assert isinstance(description, ServerDescription)
    assert [m.descriptor.full_name for m in description.services] == [
        "surmap.survey.v1.Cm5SurveyService"
    ]
    assert [(r.method, r.path) for r in description.http_routes] == [("GET", "/health/is_alive")]


def test_the_station_entrypoint_serves_the_sam_service_and_health() -> None:
    description = build_station_description()
    assert [m.descriptor.full_name for m in description.services] == [
        "surmap.survey.v1.StationSamService"
    ]
    assert [(r.method, r.path) for r in description.http_routes] == [("GET", "/health/is_alive")]
