"""
Which shop counters a town offers, and what each one sells.

Two modes, switched from the admin (GameControl.vendor_mode):

  BY_STOCK  — a vendor appears wherever the town actually has goods for it.
              Zero configuration: stock a town with swords and a weaponsmith
              shows up.
  ASSIGNED  — each town lists exactly the vendors chosen on the town record,
              so a hamlet can lack a magic shop even if it stocks a charm.

Vendor *behaviour* keys off VendorKind; everything else about a vendor (its
name, blurb, order) is data, so a replacement world can rename or reshuffle the
whole cast without code changes.
"""
from .models import EquipSlot, GameControl, Town, Vendor, VendorKind, VendorMode

GEAR_KINDS = {VendorKind.WEAPONS, VendorKind.ARMOR, VendorKind.MAGIC, VendorKind.GENERAL}


def vendor_mode(control=None):
    control = control or GameControl.objects.first()
    return control.vendor_mode if control else VendorMode.BY_STOCK


def items_for_kind(kind, town):
    """The subset of a town's stock a given counter deals in.

    'Enchanted goods' are simply items carrying a special effect, which keeps the
    split entirely data-driven rather than a hardcoded item list.
    """
    stock = town.shop_items.all()
    if kind == VendorKind.WEAPONS:
        return stock.filter(slot=EquipSlot.WEAPON, special__isnull=True)
    if kind == VendorKind.ARMOR:
        return stock.filter(slot__in=[EquipSlot.ARMOR, EquipSlot.SHIELD], special__isnull=True)
    if kind == VendorKind.MAGIC:
        return stock.exclude(special__isnull=True)
    if kind == VendorKind.GENERAL:
        return stock
    return stock.none()


def maps_for_sale(character):
    """Towns the character hasn't unlocked yet — the cartographer's wares."""
    known = character.unlocked_towns.values_list("id", flat=True)
    return Town.objects.exclude(id__in=known).order_by("map_price")


def maps_for_sale_count(town):
    """Used at seed time, where there's no character: any other town could be sold."""
    return Town.objects.exclude(id=town.id).count()


def vendor_goods(vendor, town, character):
    """(items, maps) for a vendor — only one will be populated."""
    if vendor.kind == VendorKind.MAPS:
        return town.shop_items.none(), maps_for_sale(character)
    return items_for_kind(vendor.kind, town).order_by("slot", "buy_cost"), Town.objects.none()


def vendors_for_town(town, character, control=None):
    """The counters open in this town, honouring the admin's vendor mode."""
    if vendor_mode(control) == VendorMode.ASSIGNED:
        candidates = town.vendors.all()
    else:
        candidates = Vendor.objects.all()

    open_counters = []
    for vendor in candidates:
        items, maps = vendor_goods(vendor, town, character)
        count = maps.count() if vendor.kind == VendorKind.MAPS else items.count()
        if count:
            vendor.stock_count = count
            open_counters.append(vendor)
    return open_counters


def get_vendor(slug):
    return Vendor.objects.filter(slug=slug).first()
