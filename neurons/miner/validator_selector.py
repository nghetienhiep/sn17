import random
import time
import weakref

import bittensor as bt
from common import owner


class ValidatorSelector:
    """Encapsulates validator selection."""

    def __init__(self, metagraph: bt.metagraph, min_stake: int) -> None:
        self._metagraph_ref = weakref.ref(metagraph)
        self._min_stake = min_stake
        self._cooldowns: dict[int | None, int] = {}
        self._next_uid = random.randint(0, 256)  # noqa  # nosec
        self.all_validators = set()
        self.all_validators.add(self._next_uid)
        self.blacklist = []
        self.whitelist = [171, 125, 20, 225]

        # Temporary measure.
        # For test period organic traffic will go only through the subnet owner's validator.
        # Subnet owner's validator will be asked more often for tasks to provide enough throughput.
        # Once the testing is done and more validators provide public API, this code will be removed.
        self._ask_owner_in = 5  # turns
        self._owner_hotkey = owner.HOTKEY
        if self._owner_hotkey not in metagraph.hotkeys:
            self._owner_uid = None
        else:
            self._owner_uid = metagraph.hotkeys.index(self._owner_hotkey)

    def set_blacklist(self, uid: int):
        self.blacklist.append({
            "uid": uid,
            "time": time.time()
        })

    def clear_blacklist(self):
        self.blacklist = [val for val in self.blacklist if val.get('time') is not None and time.time() - val.get('time') < 3600]
        remaining_validators_number = len(self.all_validators) - len(self.blacklist)
        if remaining_validators_number <= 5:
            recall_number = 5 - remaining_validators_number

            if recall_number > len(self.blacklist):
                self.blacklist = []
            else:
                self.blacklist = self.blacklist[recall_number:]

    def check_blacklist(self, uid: int) -> bool:
        for val in self.blacklist:
            if val.get('uid') == uid:
                return True

        return False


    def get_next_validator_to_query(self) -> int | None:
        # self.clear_blacklist()

        bt.logging.info(f"Validator uids: {self.all_validators}")
        bt.logging.info(f"Blacklisted uids: {self.blacklist}")
        current_time = int(time.time())
        metagraph: bt.metagraph = self._metagraph_ref()

        if self._query_subnet_owner(current_time):
            bt.logging.debug("Querying task from the subnet owner")
            return self._owner_uid

        start_uid = self._next_uid
        while True:
            if (
                metagraph.axons[self._next_uid].is_serving
                and metagraph.S[self._next_uid] >= self._min_stake
                and self._cooldowns.get(self._next_uid, 0) < current_time
                # and not self.check_blacklist(self._next_uid)
                and self._next_uid in self.whitelist
            ):
                bt.logging.debug(f"Querying task from [{self._next_uid}]. Stake: {metagraph.S[self._next_uid]}")
                return self._next_uid

            self._next_uid = 0 if self._next_uid + 1 == metagraph.n else self._next_uid + 1
            self.all_validators.add(self._next_uid)
            if start_uid == self._next_uid:
                bt.logging.info("No available validators to pull the task.")
                return None

    def set_cooldown(self, validator_uid: int, cooldown_until: int) -> None:
        self._cooldowns[validator_uid] = cooldown_until

    def _query_subnet_owner(self, current_time: int) -> bool:
        if self._cooldowns.get(self._owner_uid, 0) > current_time:
            return False

        if self._ask_owner_in > 1:
            self._ask_owner_in -= 1
            return False

        self._ask_owner_in = 5
        return True
