import datetime
import json
import os
# import tempfile
import threading
import time
from hashlib import md5
from pathlib import Path

import sseclient
from girder_client import GirderClient, HttpError


editor = {
   'login': 'editor',
   'girderToken': ''
}

author = {
   'login': 'author',
   'girderToken': ''
}

verifier = {
   'login': 'verifier',
   'girderToken': ''
}


class AccessType:
    NONE = -1
    READ = 0
    WRITE = 1
    ADMIN = 2


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

    def __init__(self, api_url="https://girder.local.wholetale.org/api/v1"):
        self.gc = GirderClient(apiUrl=api_url)

    def set_token(self, girderToken):
        self.gc.setToken(girderToken)

    def listen_events(self):
        self.sse_handler = threading.Thread(
            target=event_listener, args=(self.gc,), daemon=False
        )
        self.sse_handler.start()

    def get_user(self, login):
        return self.gc.get("/user/", parameters={"text": login})[0]

    def get_group(self, name):
        groups = self.gc.get("/group/", parameters={"text": name})
        if groups:
            return groups[0]
        else:
            return None

    def create_group(self, name):
        group = self.get_group(name)
        if not group:
            group = self.gc.post("/group", parameters={"name": name, "public": "false"})

        # Only needed if user is not the one who created the group,
        # but in this example the editor creates the group
        # user = self.get_user(user['login'])
        # self.gc.post(f"/group/{group['_id']}/invitation",
        #     parameters={"userId": user["_id"], "quiet": "true", "force": "true"})

        return group

    def set_access(self, level, user=None, group=None):
        acls = self.gc.get("/tale/{}/access".format(self.tale["_id"]))

        if user:
            new_acl = {
                'login': user['login'],
                'level': level,
                'id': str(user['_id']),
                'flags': [],
                'name': '%s %s' % (
                    user['firstName'], user['lastName']
                )
            }

            acls['users'].append(new_acl)

        elif group:
            new_acl = {
                'id': group['_id'],
                'name': group['name'],
                'flags': [],
                'level': level
            }

            acls['groups'].append(new_acl)

        self.gc.put("/tale/{}/access".format(self.tale['_id']),
            parameters={'access': json.dumps(acls)})

    def default_image(self):
        images = self.gc.get("/image", parameters={"text": "Jupyter"})
        return images[0]

    def create_tale(self, image=None):
        if image is None:
            image = self.default_image()

        self.tale = self.gc.post("/tale", json={"imageId": image["_id"], "dataSet": []})

    def copy_tale(self):
        self.original_tale = self.tale
        self.tale = self.gc.post("/tale/{}/copy".format(self.tale["_id"]))

    def create_submission(self, name=None, path=None):
        """
        path needs to point to a directory with submission files
        """

        self.gc.upload(path.as_posix(), parentId=self.tale["workspaceId"], dryRun=False)

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

    def submit(self):
        self.gc.put("/tale/{}/relinquish".format(self.tale["_id"]), jsonResp=False)

    def test_access(self):
        self.gc.get("/tale/{}".format(self.tale["_id"]))

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


print("[*] Creating a new Manuscript as Editor")
manuscript = Manuscript()
manuscript.set_token(editor['girderToken'])

print("[*] Creating and assigning editors group")
group = manuscript.create_group("Corere Editors")
manuscript.create_tale()
manuscript.set_access(AccessType.ADMIN, group=group)

print("[*] Adding author {}".format(author['login']))
manuscript.set_access(AccessType.WRITE, manuscript.get_user(author['login']))

print("[*] Changing user to Author")
manuscript.set_token(author['girderToken'])

print("[*] Creating submission and uploading data")
path = Path(os.path.dirname(__file__)) / "example_submission"
manuscript.create_submission(name="Submission no. 1", path=path)

print("[*] Starting Author environment (this may take a while...)")
binder = manuscript.run()
print("----")
print(f"  Open your browser and go to: {binder['url']}")
print("   Make sure to run 'run_me.ipynb'")
input("   After you're done with notebook press Enter to continue...")

print("[*] Stopping environment (this may take a while...)")
manuscript.stop(binder)

print("[*] Finalizing submission (submit) as Author")
try:
    # Author relinquishes access to the tale
    manuscript.submit()
except HttpError as error:
    # Right now GC doesn't handle 204 as success
    if error.status != 204:
        print("Unexpected response {}: ".format(error.status))

print("[*] Confirm author no longer has access")
try:
    # Author gets a 403.
    manuscript.test_access()
except HttpError as error:
    print("Error accessing manuscript: {}".format(error.status))

print("[*] Adding verifier {}".format(verifier['login']))
manuscript.set_token(editor['girderToken'])
manuscript.set_access(AccessType.READ, manuscript.get_user(verifier['login']))

print("[*] Changing user to Verifier")
manuscript.set_token(verifier['girderToken'])
new_tale = manuscript.copy_tale()

print("[*] Starting Verifier environment (this may take a while...)")
binder = manuscript.run()
print("----")
print(f"  Open your browser and go to: {binder['url']}")
print("   Make sure to run 'run_me.ipynb'")
input("   After you're done with notebook press Enter to continue...")

print("[*] Stopping environment (this may take a while...)")
manuscript.stop(binder)

# with tempfile.TemporaryDirectory() as tmpdirname:
#    print("[*] Created temporary directory for submission", path)
#    manuscript.download_submission(tmpdirname)
#    print(
#        "[*] Comparing files pre/post execution "
#        "(ultimately can happen on the backend)"
#    )
#    manuscript.compare_submission(Path(tmpdirname), path)
# print("[*] Cleaning up...")
# print("Press CTRL-C to exit")
