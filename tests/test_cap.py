"""Tests for CAP 1.2 alert output."""

import unittest
import xml.etree.ElementTree as ET

from backend.cap import CAP_NS, build_cap_alert, to_xml

ZONE = {
    "id": "tawang",
    "name": "Tawang Corridor",
    "district": "Tawang, Arunachal Pradesh",
    "coordinates": [27.4728, 94.912],
}


class CapDictTests(unittest.TestCase):
    def test_severity_tracks_risk_level(self):
        crit = build_cap_alert(ZONE, {"risk_level": "Critical", "risk_score": 88})
        adv = build_cap_alert(ZONE, {"risk_level": "Advisory", "risk_score": 40})
        self.assertEqual(crit["info"]["severity"], "Extreme")
        self.assertEqual(crit["info"]["urgency"], "Immediate")
        self.assertEqual(adv["info"]["severity"], "Moderate")

    def test_area_circle_uses_zone_coordinates(self):
        cap = build_cap_alert(ZONE, {"risk_level": "High", "risk_score": 66})
        self.assertIn("27.4728,94.912", cap["info"]["area"]["circle"])

    def test_status_is_exercise_for_prototype(self):
        cap = build_cap_alert(ZONE, {"risk_level": "High", "risk_score": 66})
        self.assertEqual(cap["status"], "Exercise")

    def test_model_parameters_passed_through(self):
        cap = build_cap_alert(ZONE, {
            "risk_level": "High", "risk_score": 66,
            "api_mm": 180.4, "exceedance_ratio": 1.7,
        })
        names = {p["valueName"] for p in cap["info"]["parameter"]}
        self.assertIn("antecedent_rainfall_mm", names)
        self.assertIn("id_threshold_exceedance", names)


class CapXmlTests(unittest.TestCase):
    def test_renders_valid_cap_namespaced_xml(self):
        cap = build_cap_alert(ZONE, {"risk_level": "Critical", "risk_score": 90,
                                     "explanation": "Extreme rainfall on a steep slope."})
        root = ET.fromstring(to_xml(cap))
        self.assertEqual(root.tag, f"{{{CAP_NS}}}alert")
        self.assertEqual(root.findtext(f"{{{CAP_NS}}}status"), "Exercise")
        info = root.find(f"{{{CAP_NS}}}info")
        self.assertEqual(info.findtext(f"{{{CAP_NS}}}event"), "Landslide")
        self.assertEqual(info.findtext(f"{{{CAP_NS}}}severity"), "Extreme")

    def test_xml_escapes_special_characters(self):
        cap = build_cap_alert(ZONE, {"risk_level": "High", "risk_score": 60,
                                     "explanation": "rain & rock <slide>"})
        xml = to_xml(cap)
        self.assertNotIn("<slide>", xml)
        self.assertIn("&amp;", xml)
        ET.fromstring(xml)  # must still parse


if __name__ == "__main__":
    unittest.main()
