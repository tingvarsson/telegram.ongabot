import sys
import unittest
from datetime import timedelta
from unittest.mock import patch

from telegram import User

from ongabot import shrink
from ongabot.chat import Chat
from ongabot.shrink import (
    BOT_PATIENT_TEXT,
    MAX_TREATMENT_LENGTH,
    TREATMENTS,
    Diagnosis,
    diagnose,
    find_patient,
    render_no_file,
    render_session,
    render_shrink_message,
)
from ongabot.utils.statistics import UserStatRow
from tests import message_fixtures

ALICE = User(id=1, first_name="Alice", is_bot=False, username="AliceInLobby")
BOB = User(id=2, first_name="Bob", is_bot=False)


def _row(responses=10, didnt_bother=0, maybe=0, no_op=0, played=None, slots_avg=2.0, played_streak=0, user=ALICE):
    """A statistics row for one user; played defaults to every answer that wasn't Maybe or No-op."""
    if played is None:
        played = responses - maybe - no_op
    polls = responses + didnt_bother
    return UserStatRow(
        user=user,
        responses=responses,
        played=played,
        response_pct=responses / polls if polls else 0.0,
        play_pct=played / polls if polls else 0.0,
        played_streak=played_streak,
        slots_avg=slots_avg,
        no_op=no_op,
        maybe=maybe,
        didnt_bother=didnt_bother,
    )


class DiagnoseTest(unittest.TestCase):
    def test_too_few_polls_is_a_new_patient(self):
        self.assertEqual(diagnose(_row(responses=2)), (Diagnosis.NEW_PATIENT, "only 2 polls on file"))
        self.assertEqual(diagnose(_row(responses=0, didnt_bother=1))[1], "only 1 poll on file")

    def test_new_patient_ends_at_min_polls(self):
        self.assertNotEqual(diagnose(_row(responses=3))[0], Diagnosis.NEW_PATIENT)

    def test_ignoring_half_the_polls_is_avoidant(self):
        self.assertEqual(diagnose(_row(responses=3, didnt_bother=3)), (Diagnosis.AVOIDANT, "ignored 3 of 6 polls"))
        self.assertNotEqual(diagnose(_row(responses=4, didnt_bother=3))[0], Diagnosis.AVOIDANT)

    def test_never_answering_is_avoidant(self):
        self.assertEqual(diagnose(_row(responses=0, didnt_bother=5))[0], Diagnosis.AVOIDANT)

    def test_avoidant_outranks_fence_sitting(self):
        self.assertEqual(diagnose(_row(responses=4, didnt_bother=4, maybe=4))[0], Diagnosis.AVOIDANT)

    def test_many_maybes_is_fence_sitting(self):
        self.assertEqual(
            diagnose(_row(responses=10, maybe=3)), (Diagnosis.FENCE_SITTING, "Maybe Baby 3 times in 10 answers")
        )
        self.assertNotEqual(diagnose(_row(responses=10, maybe=2))[0], Diagnosis.FENCE_SITTING)

    def test_singular_counts_read_naturally(self):
        self.assertEqual(diagnose(_row(responses=2, didnt_bother=1, maybe=1))[1], "Maybe Baby 1 time in 2 answers")

    def test_many_no_ops_is_couch_attachment(self):
        self.assertEqual(diagnose(_row(responses=10, no_op=4)), (Diagnosis.COUCH, "No-op 4 times in 10 answers"))
        self.assertNotEqual(diagnose(_row(responses=10, no_op=3))[0], Diagnosis.COUCH)

    def test_fence_sitting_outranks_couch(self):
        self.assertEqual(diagnose(_row(responses=10, maybe=3, no_op=5))[0], Diagnosis.FENCE_SITTING)

    def test_picking_many_slots_is_hoarding(self):
        self.assertEqual(
            diagnose(_row(responses=5, slots_avg=4.0)), (Diagnosis.SLOT_HOARDING, "averages 4.0 slots a night")
        )
        self.assertNotEqual(diagnose(_row(responses=5, slots_avg=3.9))[0], Diagnosis.SLOT_HOARDING)

    def test_hoarding_needs_a_few_nights_played(self):
        self.assertNotEqual(diagnose(_row(responses=3, no_op=1, played=2, slots_avg=5.0))[0], Diagnosis.SLOT_HOARDING)

    def test_playing_most_nights_is_lobby_dependency(self):
        self.assertEqual(
            diagnose(_row(responses=10, didnt_bother=0, played=8, played_streak=4)),
            (Diagnosis.LOBBY_DEPENDENCY, "played 8 of 10 polls, streak 4"),
        )

    def test_everyone_else_is_unremarkable(self):
        self.assertEqual(
            diagnose(_row(responses=6, didnt_bother=4, played=5)),
            (Diagnosis.UNREMARKABLE, "answered 60%, played 50%"),
        )


class FindPatientTest(unittest.TestCase):
    def setUp(self):
        self.rows = [_row(user=ALICE), _row(user=BOB)]

    def test_finds_by_user_id(self):
        self.assertIs(find_patient(self.rows, user_id=2), self.rows[1])

    def test_finds_by_username_in_any_case(self):
        self.assertIs(find_patient(self.rows, username="aliceinlobby"), self.rows[0])

    def test_misses_return_none(self):
        self.assertIsNone(find_patient(self.rows, user_id=3))
        self.assertIsNone(find_patient(self.rows, username="nobody"))


class RenderTest(unittest.TestCase):
    def test_session_names_patient_diagnosis_findings_and_treatment(self):
        with patch("ongabot.shrink.deal", return_value="TREAT") as deal:
            text = render_session("Alice", _row(responses=10, maybe=3))

        deal.assert_called_once_with(Diagnosis.FENCE_SITTING, TREATMENTS[Diagnosis.FENCE_SITTING])
        self.assertEqual(
            text,
            "The doctor will see you now, Alice.\n"
            "Diagnosis: Chronic Fence-Sitting\n"
            "Findings: Maybe Baby 3 times in 10 answers\n"
            "Treatment: TREAT",
        )

    def test_no_file_names_who(self):
        self.assertIn("No file on @x", render_no_file("@x"))

    def test_a_bot_is_turned_away(self):
        bot = User(id=9, first_name="Bot", is_bot=True)
        self.assertEqual(render_shrink_message(message_fixtures.chat(), user=bot), BOT_PATIENT_TEXT)

    def test_a_user_from_history_gets_a_session(self):
        tommy = message_fixtures.users()[0]
        text = render_shrink_message(message_fixtures.chat(), user=tommy)
        self.assertTrue(text.startswith("The doctor will see you now, Tommy."))

    def test_a_user_never_seen_has_no_file(self):
        stranger = User(id=77, first_name="Stranger", is_bot=False)
        self.assertEqual(render_shrink_message(message_fixtures.chat(), user=stranger), render_no_file("Stranger"))

    def test_username_is_looked_up_in_history(self):
        chat = Chat(message_fixtures.CHAT_ID)
        for week in range(3):
            event = message_fixtures.event(
                message_fixtures.FIRST_EVENT + timedelta(weeks=week), [BOB, ALICE], [(0,), (1,)]
            )
            chat.events[event.event_date] = event

        text = render_shrink_message(chat, username="aliceinlobby")

        self.assertTrue(text.startswith("The doctor will see you now, Alice.\n"))

    def test_unknown_username_has_no_file(self):
        self.assertEqual(render_shrink_message(message_fixtures.chat(), username="ghost"), render_no_file("@ghost"))

    def test_needs_a_user_or_a_username(self):
        with self.assertRaises(ValueError):
            render_shrink_message(message_fixtures.chat())


class TreatmentsTest(unittest.TestCase):
    def test_every_diagnosis_has_ten_unique_short_treatments(self):
        self.assertEqual(set(TREATMENTS), set(Diagnosis))
        for diagnosis, lines in TREATMENTS.items():
            with self.subTest(diagnosis=diagnosis):
                self.assertEqual(len(lines), 10)
                self.assertEqual(len(set(lines)), len(lines))
                for line in lines:
                    self.assertLessEqual(len(line), MAX_TREATMENT_LENGTH, line)

    def test_treatments_do_not_repeat_within_a_deck(self):
        # Bot code imports quips as a top-level module, so that is the one holding shrink's decks.
        decks = sys.modules[shrink.deal.__module__]
        decks._bags.pop(Diagnosis.COUCH, None)
        lines = TREATMENTS[Diagnosis.COUCH]
        dealt = [shrink.deal(Diagnosis.COUCH, lines) for _ in lines]
        self.assertEqual(sorted(dealt), sorted(lines))


if __name__ == "__main__":
    unittest.main()
