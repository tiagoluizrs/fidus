from pathlib import Path

from fidus.core.paths import default_data_dir, legacy_data_dir, migrate_legacy


def test_default_data_dir_por_sistema(tmp_path):
    assert default_data_dir({"APPDATA": "C:\\Users\\v\\AppData\\Roaming"}, "win32", tmp_path) == Path("C:\\Users\\v\\AppData\\Roaming") / "Fidus"
    assert default_data_dir({}, "linux", tmp_path) == tmp_path / ".fidus"
    assert default_data_dir({}, "win32", tmp_path) == tmp_path / ".fidus"  # sem APPDATA, cai na pasta antiga
    assert default_data_dir({"FIDUS_HOME": "/x", "APPDATA": "/a"}, "win32", tmp_path) == Path("/x")


def test_migra_copiando_sem_apagar_a_antiga(tmp_path):
    old, new = legacy_data_dir(tmp_path), tmp_path / "Roaming" / "Fidus"
    (old / "memoria").mkdir(parents=True)
    (old / "memoria" / "perfil.md").write_text("- gosta de café")
    (old / "settings.json").write_text("{}")
    (old / "speech_cache").mkdir()
    (old / "speech_cache" / "a.wav").write_bytes(b"x")
    assert migrate_legacy(new, old) is True
    assert (new / "memoria" / "perfil.md").read_text() == "- gosta de café"
    assert not (new / "speech_cache").exists()  # cache não vale a cópia
    assert (old / "memoria" / "perfil.md").exists()  # a pasta antiga fica intacta


def test_nao_migra_por_cima_de_dados_existentes(tmp_path):
    old, new = legacy_data_dir(tmp_path), tmp_path / "novo"
    old.mkdir()
    (old / "a").write_text("velho")
    new.mkdir()
    (new / "b").write_text("novo")
    assert migrate_legacy(new, old) is False
    assert not (new / "a").exists()


def test_sem_pasta_antiga_ou_igual_nao_faz_nada(tmp_path):
    assert migrate_legacy(tmp_path / "n", tmp_path / "nao-existe") is False
    assert migrate_legacy(tmp_path, tmp_path) is False


def test_subpasta_do_electron_nao_impede_a_migracao(tmp_path):
    old, new = legacy_data_dir(tmp_path), tmp_path / "Fidus"
    old.mkdir()
    (old / "settings.json").write_text("{}")
    (new / "app").mkdir(parents=True)
    assert migrate_legacy(new, old) is True
    assert (new / "settings.json").exists()
