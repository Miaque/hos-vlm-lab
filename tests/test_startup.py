import pytest

from hos_vlm_lab import main
from hos_vlm_lab.config import load_config


@pytest.mark.parametrize("with_env_file", [True, False])
def test_startup_loads_dotenv_without_overriding_environment(monkeypatch, tmp_path, with_env_file):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VLM_API_KEY", raising=False)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    monkeypatch.setenv("VLM_BASE_URL", "https://environment.test/v1")
    if with_env_file:
        (tmp_path / ".env").write_text(
            'VLM_API_KEY="file-secret"\nVLM_BASE_URL=https://file.test/v1\n',
            encoding="utf-8-sig",
        )
    configs = []
    monkeypatch.setattr("hos_vlm_lab.app.create_app", lambda: configs.append(load_config()))
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)

    main()

    assert len(configs) == 1
    model = configs[0].models[0]
    assert model.api_key == ("file-secret" if with_env_file else "")
    assert model.api_url == "https://environment.test/v1/chat/completions"
