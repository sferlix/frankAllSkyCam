'''
Unit tests for fileManager.saveSecondImageToFTP: the optional second copy of the sky image,
uploaded to another folder with another file name (config.txt [ftp] 2ndImageFolder and
2ndImageFile). saveToFTP is replaced by a recorder, so no network is used.
'''

from configparser import ConfigParser

import pytest

from frankAllSkyCam import fileManager


@pytest.fixture
def uploads(monkeypatch):
    calls = []
    monkeypatch.setattr(fileManager, "saveToFTP", lambda *a: calls.append(a))
    return calls


def _upload(folder, name, is_ftp=True):
    return fileManager.saveSecondImageToFTP(is_ftp, "/img/skycam_1.jpg", "ftp.example.org", "user", "pw",
                                            folder, name)


def test_uploads_the_image_to_the_other_folder_and_name(uploads):
    assert _upload("/webcam2/", "sky2.jpg") is True
    assert uploads == [(True, "/img/skycam_1.jpg", "ftp.example.org", "user", "pw", "/webcam2/sky2.jpg")]


def test_jpg_is_added_when_the_name_has_no_extension(uploads):
    _upload("/webcam2", "sky2")
    assert uploads[0][-1] == "/webcam2/sky2.jpg"


@pytest.mark.parametrize("name", ["sky2.jpg", "sky2.JPG", "sky2.jpeg"])
def test_an_existing_jpg_extension_is_kept(uploads, name):
    _upload("/webcam2", name)
    assert uploads[0][-1] == "/webcam2/" + name


@pytest.mark.parametrize("folder,name", [("/webcam2", "sky2.jpg"), ("/webcam2/", "sky2.jpg"),
                                         ("/webcam2/", "/sky2.jpg"), ("/webcam2//", "sky2.jpg")])
def test_slashes_between_folder_and_name_are_normalized(uploads, folder, name):
    _upload(folder, name)
    assert uploads[0][-1] == "/webcam2/sky2.jpg"


@pytest.mark.parametrize("folder,name", [("", ""), ("/webcam2/", ""), ("", "sky2.jpg"), ("  ", "sky2.jpg"),
                                         ("/webcam2/", "   "), (None, "sky2.jpg")])
def test_both_parameters_are_needed(uploads, folder, name):
    assert _upload(folder, name) is False
    assert uploads == []


def test_the_master_ftp_switch_is_passed_through(uploads):
    # saveToFTP itself returns early when isFTP is False: nothing is sent without it
    _upload("/webcam2/", "sky2.jpg", is_ftp=False)
    assert uploads[0][0] is False


def test_it_never_raises(monkeypatch):
    def boom(*a):
        raise OSError("connection reset")

    monkeypatch.setattr(fileManager, "saveToFTP", boom)
    assert _upload("/webcam2/", "sky2.jpg") is False


@pytest.mark.parametrize("ini", [
    "[ftp]\nisFTP=True\n",                                        # keys missing (existing config.txt)
    "[ftp]\nisFTP=True\n2ndImageFolder =\n2ndImageFile =\n",       # keys present but empty (defaults)
    "[ftp]\nisFTP=True\n2ndImageFolder = /other/\n",               # only one of the two
    "[ftp]\nisFTP=True\n2ndImageFile = sky2\n",
])
def test_missing_or_empty_config_keys_mean_no_second_upload(uploads, ini):
    # read the keys exactly as __main__.py does
    config = ConfigParser()
    config.read_string(ini)
    folder = config.get('ftp', '2ndImageFolder', fallback='')
    name = config.get('ftp', '2ndImageFile', fallback='')

    assert _upload(folder, name) is False
    assert uploads == []
