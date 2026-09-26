#!/usr/bin/env python3
"""Tests du gestionnaire de services de carte hors ligne (Docker simulé).

On ne lance aucun vrai conteneur ici : un faux « docker » enregistre les
commandes reçues, ce qui permet de vérifier précisément les règles qui
corrigent le bug hors ligne (jamais de suppression de Nominatim, --config
et non --file, --restart unless-stopped, pas de repli internet silencieux).
"""

import json
import sys
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from nova import map_services as ms
from nova import navigation


class FakeDocker:
    """Faux client docker : conteneurs = {nom: {status, policy, cmd}}."""

    def __init__(self, containers=None, images=("img",), fail=None):
        self.containers = containers or {}
        self.images = set(images)
        self.fail = fail          # message d'erreur à lever sur toute commande
        self.calls = []

    def __call__(self, args, timeout=30):
        self.calls.append(args)
        if self.fail:
            raise ms.DockerError(self.fail)
        if args[0] == "inspect":
            name = args[-1]
            if name not in self.containers:
                raise ms.DockerError("Error: No such object: " + name)
            c = self.containers[name]
            fmt = args[2]
            if "State.Status" in fmt:
                return c["status"]
            if "RestartPolicy" in fmt:
                return c["policy"]
            if "Config.Cmd" in fmt:
                return json.dumps(c.get("cmd"))
        if args[:2] == ["image", "inspect"]:
            if args[2] not in self.images:
                raise ms.DockerError("Error: No such image")
            return "[]"
        if args[0] == "update":
            self.containers[args[-1]]["policy"] = args[2]
            return ""
        if args[0] == "start":
            self.containers[args[1]]["status"] = "running"
            return ""
        if args[0] == "rm":
            self.containers.pop(args[-1], None)
            return ""
        if args[0] == "run":
            name = args[args.index("--name") + 1]
            self.containers[name] = {"status": "running",
                                     "policy": args[args.index("--restart") + 1],
                                     "cmd": args[args.index("img") + 1:]}
            return "id"
        return ""


def _spec(tmp_path, ok=False, stateless=False, cmd=None, name="nova-x"):
    data = tmp_path / "data.bin"
    data.write_text("x")
    return ms.ServiceSpec("tiles", "Carte", name, "img", ["-p", "1:1"],
                          [str(data)], lambda: (ok, "ne répond pas"),
                          image_cmd=cmd, stateless=stateless)


def test_conteneur_absent_cree_avec_restart_et_config(tmp_path):
    docker = FakeDocker()
    svc = ms.MapServices([_spec(tmp_path, cmd=["--config", "/data/config.json"])],
                         docker=docker)
    svc.check_now()
    run = [c for c in docker.calls if c[0] == "run"][0]
    assert "--restart" in run and "unless-stopped" in run
    assert run[-2:] == ["--config", "/data/config.json"]
    assert "--file" not in run
    assert svc.status("tiles")[0] == ms.STARTING


def test_conteneur_arrete_redemarre_sans_suppression(tmp_path):
    docker = FakeDocker({"nova-x": {"status": "exited", "policy": "no"}})
    svc = ms.MapServices([_spec(tmp_path)], docker=docker)
    svc.check_now()
    assert ["start", "nova-x"] in docker.calls
    # la politique de redémarrage est corrigée SANS recréer le conteneur
    assert ["update", "--restart", "unless-stopped", "nova-x"] in docker.calls
    assert not any(c[0] in ("rm", "run") for c in docker.calls)


def test_nominatim_jamais_supprime_meme_mal_configure(tmp_path):
    # stateless=False (cas Nominatim) : même avec d'autres arguments, on ne
    # touche pas au conteneur — sa base serait perdue.
    docker = FakeDocker({"nova-x": {"status": "running", "policy": "unless-stopped",
                                    "cmd": ["autre"]}})
    svc = ms.MapServices([_spec(tmp_path, cmd=["--config", "x"])], docker=docker)
    svc.check_now()
    assert not any(c[0] in ("rm", "run") for c in docker.calls)


def test_tileserver_lance_avec_file_est_recree(tmp_path):
    # L'ancien bug : TileServer lancé avec --file -> recréé avec --config.
    docker = FakeDocker({"nova-x": {"status": "running", "policy": "no",
                                    "cmd": ["--file", "tunisia.mbtiles"]}})
    svc = ms.MapServices([_spec(tmp_path, stateless=True,
                                cmd=["--config", "/data/config.json"])],
                         docker=docker)
    svc.check_now()
    assert docker.containers["nova-x"]["cmd"] == ["--config", "/data/config.json"]
    assert docker.containers["nova-x"]["policy"] == "unless-stopped"


def test_service_pret_ne_touche_pas_au_conteneur(tmp_path):
    docker = FakeDocker({"nova-x": {"status": "running", "policy": "unless-stopped"}})
    svc = ms.MapServices([_spec(tmp_path, ok=True)], docker=docker)
    svc.check_now()
    svc.check_now()
    assert svc.status("tiles") == (ms.READY, "")
    # une seule lecture de la politique, jamais de start/run/rm
    assert docker.calls == [["inspect", "-f", "{{.HostConfig.RestartPolicy.Name}}",
                             "nova-x"]]


def test_service_pret_sans_restart_est_corrige(tmp_path):
    # Cas réel observé : Valhalla/Nominatim fonctionnels mais en restart=no,
    # donc perdus au prochain reboot du Pi.
    docker = FakeDocker({"nova-x": {"status": "running", "policy": "no"}})
    svc = ms.MapServices([_spec(tmp_path, ok=True)], docker=docker)
    svc.check_now()
    assert docker.containers["nova-x"]["policy"] == "unless-stopped"
    assert not any(c[0] in ("start", "rm", "run") for c in docker.calls)


def test_docker_inaccessible_donne_une_cause_claire(tmp_path):
    docker = FakeDocker(fail=ms.explain_docker_error(
        "permission denied while trying to connect to the Docker daemon socket"))
    svc = ms.MapServices([_spec(tmp_path)], docker=docker)
    svc.check_now()
    state, reason = svc.status("tiles")
    assert state == ms.DOWN
    assert "groupe docker" in reason


def test_image_absente_hors_ligne_signalee(tmp_path):
    docker = FakeDocker(images=())
    svc = ms.MapServices([_spec(tmp_path)], docker=docker)
    svc.check_now()
    state, reason = svc.status("tiles")
    assert state == ms.DOWN and "docker pull" in reason


def test_fichier_de_donnees_manquant_signale(tmp_path):
    spec = _spec(tmp_path)
    spec.required = [str(tmp_path / "absent.mbtiles")]
    svc = ms.MapServices([spec], docker=FakeDocker())
    svc.check_now()
    state, reason = svc.status("tiles")
    assert state == ms.DOWN and "absent.mbtiles" in reason


def test_listener_notifie_les_changements(tmp_path):
    vus = []
    svc = ms.MapServices([_spec(tmp_path, ok=True)], docker=FakeDocker())
    svc.add_listener(lambda snap: vus.append(snap["tiles"][0]))
    svc.check_now()
    svc.check_now()          # pas de changement -> pas de 2e notification
    assert vus == [ms.READY]


def test_specs_par_defaut_utilisent_config_et_restart():
    specs = {s.key: s for s in ms.default_specs()}
    assert specs["tiles"].image_cmd == ["--config", "/data/config.json"]
    assert specs["tiles"].stateless is True
    assert specs["geocoding"].stateless is False


# ─── navigation : pas de repli internet silencieux ──────────────────────

def test_geocode_hors_ligne_sans_repli_internet(monkeypatch):
    monkeypatch.setattr(navigation, "_map_config", lambda: {})
    monkeypatch.setattr(navigation, "_nominatim_local_search",
                        lambda *a, **k: None)
    appels = []
    monkeypatch.setattr(navigation, "_nominatim_search",
                        lambda *a, **k: appels.append("osm") or [])
    assert navigation.geocode("tunis") == []
    assert appels == []                      # internet jamais sollicité
    assert "Nominatim local ne répond pas" in navigation.last_failure()


def test_geocode_repli_internet_si_autorise(monkeypatch):
    monkeypatch.setattr(navigation, "_map_config",
                        lambda: {"allow_online_fallback": True})
    monkeypatch.setattr(navigation, "_nominatim_local_search",
                        lambda *a, **k: None)
    monkeypatch.setattr(navigation, "_nominatim_search",
                        lambda *a, **k: [{"name": "Tunis", "lat": 1, "lon": 2}])
    assert navigation.geocode("tunis")[0]["name"] == "Tunis"
    assert navigation.last_source() == "en ligne"


def test_route_hors_ligne_sans_repli_internet(monkeypatch):
    monkeypatch.setattr(navigation, "_map_config", lambda: {})
    monkeypatch.setattr(navigation, "_route_valhalla", lambda *a, **k: None)
    monkeypatch.setattr(navigation.time, "sleep", lambda s: None)
    appels = []
    monkeypatch.setattr(navigation, "_route_ors",
                        lambda *a, **k: appels.append("ors"))
    assert navigation.route(36.8, 10.1, 36.9, 10.2) is None
    assert appels == []


def test_boucle_de_plantage_signalee_sans_relance(tmp_path, monkeypatch):
    # Cas réel sur la Pi : Nominatim en « restarting » permanent
    docker = FakeDocker({"nova-x": {"status": "restarting", "policy": "unless-stopped"}})
    svc = ms.MapServices([_spec(tmp_path)], docker=docker)
    monkeypatch.setattr(svc, "_journal",
                        lambda spec: ["FATAL: database \"nominatim\" already exists"])
    svc.check_now()
    state, reason = svc.status("tiles")
    assert state == ms.DOWN and "plante en boucle" in reason and "already exists" in reason
    assert not any(c[0] in ("start", "rm", "run") for c in docker.calls)


JOURNAL_CORROMPU = [
    "LOG:  database system was interrupted; last known up at 2026-09-23 21:18:49 UTC",
    "LOG:  invalid checkpoint record",
    "PANIC:  could not locate a valid checkpoint record",
    "FATAL: Creating new database failed.",
]


def _spec_nominatim(tmp_path):
    spec = _spec(tmp_path)
    spec.volumes = ["nova-nominatim-db"]
    spec.signatures_corruption = ["could not locate a valid checkpoint record"]
    spec.demarrage_long = "import en cours — ne pas éteindre le Pi"
    return spec


def test_base_corrompue_reparee_automatiquement(tmp_path, monkeypatch):
    # Cas réel de la Pi : import interrompu -> PostgreSQL irrécupérable
    docker = FakeDocker({"nova-x": {"status": "restarting", "policy": "unless-stopped"}})
    svc = ms.MapServices([_spec_nominatim(tmp_path)], docker=docker)
    monkeypatch.setattr(svc, "_journal", lambda spec: JOURNAL_CORROMPU)
    svc.check_now()
    commandes = [c[:2] for c in docker.calls]
    assert ["rm", "-f"] in commandes                       # conteneur supprimé
    assert ["volume", "rm", "-f", "nova-nominatim-db"] in docker.calls   # base supprimée
    assert docker.containers["nova-x"]["status"] == "running"             # recréé
    state, reason = svc.status("tiles")
    assert state == ms.STARTING and "ne pas éteindre" in reason


def test_reparation_au_plus_une_fois_par_heure(tmp_path, monkeypatch):
    docker = FakeDocker({"nova-x": {"status": "restarting", "policy": "unless-stopped"}})
    svc = ms.MapServices([_spec_nominatim(tmp_path)], docker=docker)
    monkeypatch.setattr(svc, "_journal", lambda spec: JOURNAL_CORROMPU)
    svc.check_now()
    docker.containers["nova-x"]["status"] = "restarting"   # nouvel échec
    docker.calls.clear()
    svc.check_now()
    assert not any(c[0] == "run" for c in docker.calls)    # pas de 2e réimport
    assert svc.status("tiles")[0] == ms.DOWN


def test_import_long_jamais_declare_en_panne(tmp_path, monkeypatch):
    docker = FakeDocker({"nova-x": {"status": "running", "policy": "unless-stopped"}})
    svc = ms.MapServices([_spec_nominatim(tmp_path)], docker=docker)
    monkeypatch.setattr(ms, "STARTUP_TIMEOUT", 0)          # délai dépassé
    svc.check_now()
    state, reason = svc.status("tiles")
    assert state == ms.STARTING and "ne pas éteindre" in reason
