"""
Tests for Universal Unit Conversion across Inches, Meters, Centimeters, Millimeters, and Feet.
Validates:
1. Normalization of metric, imperial, and continuous dimensions.
2. Order-agnostic and metric photo dimensions (e.g. 10x15 cm, 15x20 cm, 20 by 30 cm).
3. End-to-end qualification and catalogue filter routing based on units.
"""

import pytest
from conversation.canonical_entity_normalizer import CanonicalEntityNormalizer
from catalog.catalogue_filter import catalogue_filter
from catalog.subcategory_resolver import resolve_subcategory
from conversation.normalizer import extract_deterministic_requirements


def test_meter_conversions():
    """Validates meter unit conversions to standard commercial printer widths."""
    # 0.6m -> 24"
    res1 = CanonicalEntityNormalizer.normalize_dimensions("I need a 0.6 meter wide plotter")
    assert res1["print_width"] == 24
    assert res1["paper_size"] == "a1"

    # 0.9m -> 36"
    res2 = CanonicalEntityNormalizer.normalize_dimensions("looking for a 0.9m CAD printer")
    assert res2["print_width"] == 36
    assert res2["paper_size"] == "a0"

    # 1 meter -> 44" (since 36" = 0.914m is too small to fit 1.0m)
    res3 = CanonicalEntityNormalizer.normalize_dimensions("I need a 1 meter wide plotter")
    assert res3["print_width"] == 44
    assert res3["paper_size"] == "44-inch"

    # 1.1m -> 44"
    res4 = CanonicalEntityNormalizer.normalize_dimensions("1.1m wide large format printer")
    assert res4["print_width"] == 44

    # 1.6m -> 64"
    res5 = CanonicalEntityNormalizer.normalize_dimensions("1.6 meter production printer")
    assert res5["print_width"] == 64
    assert res5["paper_size"] == "64-inch"


def test_centimeter_conversions():
    """Validates centimeter unit conversions to standard printer classes."""
    # 60cm / 61cm -> 24"
    res1 = CanonicalEntityNormalizer.normalize_dimensions("60 cm plotter")
    assert res1["print_width"] == 24
    assert res1["paper_size"] == "a1"

    res2 = CanonicalEntityNormalizer.normalize_dimensions("61cm wide plotter")
    assert res2["print_width"] == 24

    # 90cm / 91.4cm -> 36"
    res3 = CanonicalEntityNormalizer.normalize_dimensions("90 cm wide printer")
    assert res3["print_width"] == 36
    assert res3["paper_size"] == "a0"

    # 100cm / 110cm -> 44"
    res4 = CanonicalEntityNormalizer.normalize_dimensions("100cm wide plotter")
    assert res4["print_width"] == 44

    res5 = CanonicalEntityNormalizer.normalize_dimensions("110 cm large format")
    assert res5["print_width"] == 44

    # 160cm -> 64"
    res6 = CanonicalEntityNormalizer.normalize_dimensions("160cm wide printer")
    assert res6["print_width"] == 64

    # 33cm -> 13" (A3+)
    res7 = CanonicalEntityNormalizer.normalize_dimensions("33 cm photo printer")
    assert res7["print_width"] == 13
    assert res7["paper_size"] == "a3+"

    # 43cm -> 17" (A2+)
    res8 = CanonicalEntityNormalizer.normalize_dimensions("43 cm photo printer")
    assert res8["print_width"] == 17
    assert res8["paper_size"] == "a2+"


def test_feet_conversions():
    """Validates feet/ft unit conversions to standard printer classes."""
    # 2 feet -> 24"
    res1 = CanonicalEntityNormalizer.normalize_dimensions("2 feet wide plotter")
    assert res1["print_width"] == 24

    res2 = CanonicalEntityNormalizer.normalize_dimensions("2ft printer")
    assert res2["print_width"] == 24

    # 3 feet -> 36"
    res3 = CanonicalEntityNormalizer.normalize_dimensions("3 feet wide printer")
    assert res3["print_width"] == 36

    res4 = CanonicalEntityNormalizer.normalize_dimensions("3ft wide plotter")
    assert res4["print_width"] == 36

    # 4 feet -> 48 inches -> requires 64" printer (since 44" is only 3.67 ft)
    res5 = CanonicalEntityNormalizer.normalize_dimensions("4 feet wide large format printer")
    assert res5["print_width"] == 64

    # 5 feet -> 64"
    res6 = CanonicalEntityNormalizer.normalize_dimensions("5 feet wide printer")
    assert res6["print_width"] == 64


def test_metric_photo_sizes():
    """Validates photo prints in cm (e.g. 10x15 cm, 15x20 cm, 20x30 cm)."""
    # 10x15 cm -> 4x6
    res1 = CanonicalEntityNormalizer.normalize_dimensions("10x15 cm photo prints")
    assert "4x6" in res1["print_sizes"]

    # 15x20 cm -> 6x8
    res2 = CanonicalEntityNormalizer.normalize_dimensions("15x20 cm photos")
    assert "6x8" in res2["print_sizes"]

    # 20 by 30 cm -> 8x12
    res3 = CanonicalEntityNormalizer.normalize_dimensions("20 by 30 cm photo prints")
    assert "8x12" in res3["print_sizes"]

    # 13x18 cm -> 5x7
    res4 = CanonicalEntityNormalizer.normalize_dimensions("13x18 cm photo prints")
    assert "5x7" in res4["print_sizes"]


def test_end_to_end_filter_with_units():
    """Validates end-to-end catalogue filtering when customer specifies units in feet or meters."""
    # 1. Customer asks for "3 feet wide plotter without scanner"
    reqs, _ = extract_deterministic_requirements("I need a 3 feet wide CAD plotter without scanner", category="technical_large_format")
    subcat = resolve_subcategory("technical_large_format", reqs)
    assert subcat == "technical_36_print_only"

    cards, no_match = catalogue_filter.filter_and_rank(category="technical_large_format", subcategory=subcat, requirements=reqs)
    assert len(cards) >= 1
    assert no_match is None

    # 2. Customer asks for "60 cm printer for architectural blueprints"
    reqs2, _ = extract_deterministic_requirements("60 cm printer for architectural blueprints", category="technical_large_format")
    subcat2 = resolve_subcategory("technical_large_format", reqs2)
    assert subcat2 == "technical_24_print_only"
    cards2, no_match2 = catalogue_filter.filter_and_rank(category="technical_large_format", subcategory=subcat2, requirements=reqs2)
    assert len(cards2) >= 1
    assert no_match2 is None

    # 3. Customer asks for "1 meter wide printer with scanner"
    reqs3, _ = extract_deterministic_requirements("I need a 1 meter wide printer with integrated scanner", category="technical_large_format")
    subcat3 = resolve_subcategory("technical_large_format", reqs3)
    assert subcat3 == "technical_44_multifunction"
    cards3, no_match3 = catalogue_filter.filter_and_rank(category="technical_large_format", subcategory=subcat3, requirements=reqs3)
    assert len(cards3) >= 1
    assert no_match3 is None
