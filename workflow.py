import datetime
import json
import os
import tempfile
import threading
import time
from hashlib import md5
from pathlib import Path

import sseclient
from girder_client import GirderClient


class InstanceStatus:
    LAUNCHING = 0
    RUNNING = 1
    ERROR = 2


def md5sum(filename, buf_size=8192):
    m = md5()
    # the with statement makes sure the file will be closed
    if filename.is_dir():
        return
    with open(filename, "rb") as f:
        # We read the file in small chunk until EOF
        data = f.read(buf_size)
        while data:
            # We had data to the md5 hash
            m.update(data)
            data = f.read(buf_size)
    # We return the md5 hash in hex
    return m.hexdigest()


def event_listener(gc):
    stream = gc.sendRestRequest(
        "GET",
        "/notification/stream",
        stream=True,
        headers={"Accept": "text/event-stream"},
        jsonResp=False,
        parameters={"since": int(datetime.datetime.now().timestamp())},
    )
    client = sseclient.SSEClient(stream)
    for event in client.events():
        data = json.loads(event.data)
        if data["type"] == "wt_progress":
            progress = int(data["data"]["current"] / data["data"]["total"] * 100.0)
            msg = (
                "  -> event received:"
                f" msg = {data['data']['message']}"
                f" status = {data['data']['state']}"
                f" progress = {progress}%"
            )
            print(msg)


class Manuscript:
    """Pseudo core2 <-> WT interface.

    We are going to map Manuscript to Tale and Submission to Version.
    """

    def __init__(self, api_url="https://girder.stage.wholetale.org/api/v1"):
        self.gc = GirderClient(apiUrl=api_url)
        self.gc.authenticate(apiKey=os.environ.get("GIRDER_API_KEY"))
        self.tale = self.create_tale()
        self.sse_handler = threading.Thread(
            target=event_listener, args=(self.gc,), daemon=False
        )
        self.sse_handler.start()

    def default_image(self):
        images = self.gc.get("/image", parameters={"text": "Jupyter"})
        return images[0]

    def create_tale(self, image=None):
        if image is None:
            image = self.default_image()

        tale = self.gc.post("/tale", json={"imageId": image["_id"], "dataSet": []})
        return tale

    def create_submission(self, name=None, path=None):
        """
        path needs to point to a directory with submission files
        """
        # upload path
        for fname in path.iterdir():
            self.gc.uploadFileToFolder(self.tale["workspaceId"], fname)

        # Finalize an immutable "submission"
        parameters = {"taleId": self.tale["_id"]}
        if name is not None:
            parameters["name"] = name
        version = self.gc.post("/version", parameters=parameters)
        return version

    def run(self, submissionId=None):
        if submissionId is not None:
            print("We would revert to that version. Pass now")
        instance = self.gc.post("/instance", parameters={"taleId": self.tale["_id"]})
        while instance["status"] == InstanceStatus.LAUNCHING:
            time.sleep(2)
            instance = self.gc.get(f"/instance/{instance['_id']}")
        return instance

    def stop(self, instance):
        self.gc.delete(f"/instance/{instance['_id']}")

    def download_submission(self, path, folder_id=None):
        if folder_id is None:
            folder_id = self.tale["workspaceId"]  # otherwise it should be version

        self.gc.downloadFolderRecursive(folder_id, path)

    @staticmethod
    def compare_submission(new, old):
        new_files = set(_.name for _ in new.iterdir())
        old_files = set(_.name for _ in old.iterdir())

        if diff := new_files - old_files:
            print("    New files:")
            for name in diff:
                print(f"      -> {name}")
        if diff := old_files - new_files:
            print("    Removed files:")
            for name in diff:
                print(f"      -> {name}")
        for name in new_files & old_files:
            new_sum = md5sum(new / name)
            old_sum = md5sum(old / name)
            if new_sum != old_sum:
                print(f"File {name} was modified!!! (md5sum differs)")


print("[*] Creating a new Manuscript")
manuscript = Manuscript()
print("[*] Creating submission and uploading data")
path = Path(os.path.dirname(__file__)) / "example_submission"
manuscript.create_submission(name="Submission no. 1", path=path)
print("[*] Starting Jupyter notebook (this may take a while...)")
binder = manuscript.run()
print("----")
print(f"  Open your browser and go to: {binder['url']}")
print("   Make sure to run 'run_me.ipynb'")
input("   After you're done with notebook press Enter to continue...")
manuscript.stop(binder)
with tempfile.TemporaryDirectory() as tmpdirname:
    print("[*] Created temporary directory for submission", path)
    manuscript.download_submission(tmpdirname)
    print(
        "[*] Comparing files pre/post execution "
        "(ultimately can happen on the backend)"
    )
    manuscript.compare_submission(Path(tmpdirname), path)
print("[*] Cleaning up...")
print("Press CTRL-C to exit")
