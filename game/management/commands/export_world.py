"""Write the current game world to a portable JSON pack."""
from django.core.management.base import BaseCommand

from game import worldpack


class Command(BaseCommand):
    help = "Export all world content (monsters, items, spells, levels, drops, towns, vendors, control) to JSON."

    def add_arguments(self, parser):
        parser.add_argument("--output", "-o", default="world.json",
                            help="Where to write the pack (default: world.json)")
        parser.add_argument("--compact", action="store_true",
                            help="Write without indentation.")

    def handle(self, *args, **options):
        path = options["output"]
        data = worldpack.write_pack(path, indent=None if options["compact"] else 2)
        summary = ", ".join(
            f"{len(data[k])} {k}" for k in
            ("monsters", "items", "spells", "levels", "drops", "towns", "vendors")
        )
        self.stdout.write(self.style.SUCCESS(f"Wrote {path} — {summary}."))
