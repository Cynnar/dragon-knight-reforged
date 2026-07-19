"""Load a world pack, optionally replacing the current world outright."""
from django.core.management.base import BaseCommand, CommandError

from game import worldpack


class Command(BaseCommand):
    help = "Import world content from a JSON pack. Player accounts are never touched."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to the world pack JSON file.")
        parser.add_argument(
            "--replace", action="store_true",
            help="Delete existing world content first, instead of merging by id.",
        )
        parser.add_argument("--noinput", action="store_true",
                            help="Skip the confirmation prompt for --replace.")

    def handle(self, *args, **options):
        try:
            pack = worldpack.read_pack(options["path"])
        except FileNotFoundError:
            raise CommandError(f"No such file: {options['path']}")
        except ValueError as exc:
            raise CommandError(f"Could not read pack: {exc}")

        if options["replace"] and not options["noinput"]:
            self.stdout.write(self.style.WARNING(
                "--replace deletes ALL current world content (monsters, items, spells,\n"
                "levels, drops, towns, vendors). Characters and accounts survive, but any\n"
                "equipped or carried items that don't exist in the new pack will be lost."
            ))
            if input("Type 'yes' to continue: ").strip().lower() != "yes":
                self.stdout.write("Aborted.")
                return

        try:
            counts = worldpack.import_world(pack, replace=options["replace"])
        except ValueError as exc:
            raise CommandError(str(exc))

        summary = ", ".join(f"{v} {k}" for k, v in counts.items())
        self.stdout.write(self.style.SUCCESS(f"Imported — now holding {summary}."))
