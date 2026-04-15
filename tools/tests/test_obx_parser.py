#!/usr/bin/env python3
"""Quick smoke test for the OBX parser using the example row from CCR_LabReport."""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ccr_labreport_to_omop import parse_obx_segments, classify_obx

SAMPLE_OBX_JSON = """[{"0":"OBX","1":"1","2":"ST","3":"60573-3^Report template source^LN","5":"CAP Cancer Protocols","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"2","2":"CWE","3":"60572-5^Report template ID^LN","5":"189.100004300^INVASIVE CARCINOMA OF THE BREAST: Resection^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"3","2":"ST","3":"60574-1^Report template version ID^LN","5":"4.010.001.REL","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"4","2":"CWE","3":"58807.100004300^Procedure^CAPECC","5":"40307.100004300^Excision (less than total mastectomy)^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"5","2":"CWE","3":"16214.100004300^Specimen Laterality^CAPECC","5":"16215.100004300^Right^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"6","2":"CWE","3":"41794.100004300^Histologic Type^CAPECC","5":"16283.100004300^Invasive lobular carcinoma^CAPECC^89740008^LOBULAR CARCINOMA^SCT","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"7","2":"CWE","3":"380281.100004300^Histologic Grade (Nottingham Histologic Score)^CAPECC","5":"380283.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"8","2":"CWE","3":"38124.100004300^Glandular (Acinar) / Tubular Differentiation^CAPECC","5":"16349.100004300^Score 3^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"9","2":"CWE","3":"38125.100004300^Nuclear Pleomorphism^CAPECC","5":"16356.100004300^Score 3^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"10","2":"CWE","3":"38390.100004300^Mitotic Rate^CAPECC","5":"16383.100004300^Score 1^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"11","2":"CWE","3":"38391.100004300^Overall Grade^CAPECC","5":"16391.100004300^Grade 2 (scores of 6 or 7)^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"12","2":"CWE","3":"30148.100004300^Tumor Size^CAPECC","4":"31357","5":"31357.100004300^Greatest dimension of largest invasive focus (Millimeters)^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"13","2":"ST","3":"30148.100004300^Tumor Size^CAPECC","4":"31357","5":"45","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"14","2":"CWE","3":"38392.100004300^Tumor Focality^CAPECC","5":"16448.100004300^Single focus of invasive carcinoma^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"15","2":"CWE","3":"44040.100004300^Ductal Carcinoma In Situ (DCIS)^CAPECC","5":"16306.100004300^Not identified^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"16","2":"CWE","3":"16337.100004300^Lobular Carcinoma In Situ (LCIS)^CAPECC","5":"16339.100004300^Present^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"17","2":"CWE","3":"350913.100004300^Tumor Extent^CAPECC","5":"350914.100004300^Not applicable^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"18","2":"CWE","3":"16430.100004300^Lymphatic and / or Vascular Invasion^CAPECC","5":"16432.100004300^Present^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"19","2":"CWE","3":"820570.100004300^^CAPECC","5":"820571.100004300^Focal^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"20","2":"CWE","3":"16440.100004300^Microcalcifications^CAPECC","5":"16444.100004300^Present in non-neoplastic tissue^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"21","2":"CWE","3":"16455.100004300^Treatment Effect in the Breast^CAPECC","5":"16456.100004300^No known presurgical therapy^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"22","2":"CWE","3":"37850.100004300^Treatment Effect in the Lymph Nodes^CAPECC","5":"16462.100004300^Not applicable^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"23","2":"CWE","3":"351503.100004300^Margin Status for Invasive Carcinoma^CAPECC","5":"351504.100004300^All margins negative for invasive carcinoma^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"24","2":"CWE","3":"351505.100004300^Distance from Invasive Carcinoma to Closest Margin^CAPECC","4":"351509","5":"351509.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"25","2":"ST","3":"351505.100004300^Distance from Invasive Carcinoma to Closest Margin^CAPECC","4":"351509","5":"1.5","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"26","2":"CWE","3":"351495.100004300^Closest Margin(s) to Invasive Carcinoma^CAPECC","5":"351501.100004300^Lateral^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"27","2":"CWE","3":"351632.100004300^Margin Status for DCIS^CAPECC","5":"351654.100004300^Not applicable (no DCIS in specimen)^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"28","2":"ST","3":"351700.100004300^Margin Comment^CAPECC","5":"All other margins \u003e3 mm (inclusive of parts U,V, W)","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"29","2":"CWE","3":"351589.100004300^Regional Lymph Node Status^CAPECC","5":"374353.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"30","2":"CWE","3":"351591.100004300^^CAPECC","5":"351593.100004300^Tumor present in regional lymph node(s)^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"31","2":"CWE","3":"33611.100004300^Number of Lymph Nodes with Macrometastases^CAPECC","4":"14562","5":"14562.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"32","2":"ST","3":"33611.100004300^Number of Lymph Nodes with Macrometastases^CAPECC","4":"14562","5":"2","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"33","2":"CWE","3":"33613.100004300^Number of Lymph Nodes with Micrometastases^CAPECC","4":"15332","5":"15332.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"34","2":"ST","3":"33613.100004300^Number of Lymph Nodes with Micrometastases^CAPECC","4":"15332","5":"1","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"35","2":"CWE","3":"33615.100004300^Number of Lymph Nodes with Isolated Tumor Cells^CAPECC","4":"33616","5":"33616.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"36","2":"ST","3":"33615.100004300^Number of Lymph Nodes with Isolated Tumor Cells^CAPECC","4":"33616","5":"3","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"37","2":"CWE","3":"352296.100004300^Size of Largest Nodal Metastatic Deposit^CAPECC","4":"4135","5":"4135.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"38","2":"ST","3":"352296.100004300^Size of Largest Nodal Metastatic Deposit^CAPECC","4":"4135","5":"7","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"39","2":"CWE","3":"352303.100004300^Extranodal Extension^CAPECC","5":"16708.100004300^Not identified^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"40","2":"CWE","3":"351602.100004300^Total Number of Lymph Nodes Examined (sentinel and non-sentinel)^CAPECC","4":"351601","5":"351601.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"41","2":"ST","3":"351602.100004300^Total Number of Lymph Nodes Examined (sentinel and non-sentinel)^CAPECC","4":"351601","5":"7","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"42","2":"CWE","3":"351607.100004300^Number of Sentinel Nodes Examined^CAPECC","4":"351606","5":"351606.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"43","2":"ST","3":"351607.100004300^Number of Sentinel Nodes Examined^CAPECC","4":"351606","5":"7","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"44","2":"CWE","3":"352334.100004300^Distant Site(s) Involved^CAPECC","5":"352343.100004300^Not applicable^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"45","2":"CWE","3":"820562.100004300^Modified Classification^CAPECC","5":"820592.100004300^Not applicable^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"46","2":"CWE","3":"327740.100004300^pT Category^CAPECC","5":"16738.100004300^pT2^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"47","2":"CWE","3":"820563.100004300^T Suffix^CAPECC","5":"820564.100004300^Not applicable^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"48","2":"CWE","3":"763178.100004300^pN Category^CAPECC","5":"16765.100004300^pN1a^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"49","2":"CWE","3":"42996.100004300^N Suffix^CAPECC","5":"55616.100004300^Not applicable^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"50","2":"CWE","3":"16775.100004300^pM Category^CAPECC","5":"16778.100004300^Not applicable - pM cannot be determined from the submitted specimen(s)^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"51","2":"CWE","3":"43789.100004300^{No text}^CAPECC","5":"41776.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"52","2":"CWE","3":"45138.100004300^Estrogen Receptor (ER) Status^CAPECC","5":"42862.100004300^Positive (greater than 10% of cells demonstrate nuclear positivity)^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"53","2":"CWE","3":"41411.100004300^Percentage of Cells with Nuclear Positivity^CAPECC","4":"45587","5":"45587.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"54","2":"ST","3":"41411.100004300^Percentage of Cells with Nuclear Positivity^CAPECC","4":"45587","5":"90","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"55","2":"CWE","3":"43789.100004300^{No text}^CAPECC","5":"54634.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"56","2":"CWE","3":"42928.100004300^Progesterone Receptor (PgR) Status^CAPECC","5":"41488.100004300^Positive^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"57","2":"CWE","3":"42936.100004300^Percentage of Cells with Nuclear Positivity^CAPECC","4":"42945","5":"42945.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"58","2":"ST","3":"42936.100004300^Percentage of Cells with Nuclear Positivity^CAPECC","4":"42945","5":"90","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"59","2":"CWE","3":"43789.100004300^{No text}^CAPECC","5":"36944.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"60","2":"CWE","3":"52399.100004300^HER2 (by immunohistochemistry)^CAPECC","5":"57817.100004300^Negative (Score 1\u002b)^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"61","2":"CWE","3":"43789.100004300^{No text}^CAPECC","5":"42458.100004300^{No text}^CAPECC","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"62","2":"NM","3":"43798.100004300^Ki-67 Percentage of Positive Nuclei^CAPECC","5":"10","6":"^^UCUM","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"},{"0":"OBX","1":"63","2":"ST","3":"43743.100004300^Testing Performed on Case Number^CAPECC","5":"FP25-10911","11":"C","14":"20250918102100","15":"ST JUDE MEDICAL CENTER^05D0576873^CLIA"}]"""

obxs = parse_obx_segments(SAMPLE_OBX_JSON)
print(f"Parsed {len(obxs)} OBX segments\n")

for o in obxs:
    target = classify_obx(o)
    meta = " [META]" if o.is_metadata else ""
    print(f"  #{o.set_id} [{o.value_type}] {o.coding_system:6s} -> {target:12s}{meta}")
    print(f"       {o.identifier_text} = {o.value[:80]}")
    if o.observation_datetime:
        print(f"       datetime: {o.observation_datetime}")
    if o.responsible_observer_npi:
        print(f"       NPI: {o.responsible_observer_npi}")
    print()

# Verify expectations
assert len(obxs) == 63, f"Expected 63, got {len(obxs)}"

# OBX#1-3: report-level metadata (LOINC 60573-3, 60572-5, 60574-1) → skip
assert classify_obx(obxs[0]) == "skip", f"OBX#1 should be skip (Report template source)"
assert classify_obx(obxs[1]) == "skip", f"OBX#2 should be skip (Report template ID)"
assert (
    classify_obx(obxs[2]) == "skip"
), f"OBX#3 should be skip (Report template version ID)"

# OBX#4-5: coded clinical data (CWE/CAPECC) → observation
assert (
    classify_obx(obxs[3]) == "observation"
), f"OBX#4 (Procedure) should be observation"
assert (
    classify_obx(obxs[4]) == "observation"
), f"OBX#5 (Specimen Laterality) should be observation"

# OBX#6: Histologic Type → observation
assert (
    classify_obx(obxs[5]) == "observation"
), f"OBX#6 (Histologic Type) should be observation"
assert (
    obxs[5].identifier_text == "Histologic Type"
), f"OBX#6 identifier_text mismatch: {obxs[5].identifier_text}"

# OBX#62: Ki-67 is NM (numeric) → measurement
assert (
    classify_obx(obxs[61]) == "measurement"
), f"OBX#62 (Ki-67) should be measurement, got {classify_obx(obxs[61])}"
assert (
    obxs[61].value_type == "NM"
), f"OBX#62 value_type should be NM, got {obxs[61].value_type}"
assert obxs[61].value == "10", f"OBX#62 value should be '10', got {obxs[61].value}"

# OBX#63: Testing Performed on Case Number (ST) → observation
assert classify_obx(obxs[62]) == "observation", f"OBX#63 should be observation"

# Datetime parsed from all segments (20250918102100 format)
assert obxs[3].observation_datetime is not None, "OBX#4 should have a datetime"
assert obxs[3].observation_datetime.year == 2025, f"OBX#4 year should be 2025"
assert obxs[3].observation_datetime.month == 9, f"OBX#4 month should be 9"
assert obxs[3].observation_datetime.day == 18, f"OBX#4 day should be 18"

# Count how many of each classification
skipped = sum(1 for o in obxs if classify_obx(o) == "skip")
observations = sum(1 for o in obxs if classify_obx(o) == "observation")
measurements = sum(1 for o in obxs if classify_obx(o) == "measurement")
assert skipped == 3, f"Expected 3 skipped (metadata), got {skipped}"
assert measurements == 1, f"Expected 1 measurement (Ki-67 NM), got {measurements}"
assert observations == 59, f"Expected 59 observations, got {observations}"
assert skipped + observations + measurements == 63, "Counts should sum to total"

# New field checks: observation_sub_id (field "4"), units (field "6"), performing_org (field "15")

# OBX#12 has field "4" = "31357" (Tumor Size sub-group)
assert (
    obxs[11].observation_sub_id == "31357"
), f"OBX#12 sub_id should be '31357', got {obxs[11].observation_sub_id}"
# OBX#4 has no field "4"
assert (
    obxs[3].observation_sub_id is None
), f"OBX#4 sub_id should be None, got {obxs[3].observation_sub_id}"

# OBX#62 has field "6" = "^^UCUM" (Ki-67 units)
assert (
    obxs[61].units == "^^UCUM"
), f"OBX#62 units should be '^^UCUM', got {obxs[61].units}"
# OBX#4 has no field "6"
assert obxs[3].units is None, f"OBX#4 units should be None, got {obxs[3].units}"

# Performing org comes from field "15" (Producer's ID) when "23" is absent
assert (
    obxs[0].performing_org == "ST JUDE MEDICAL CENTER"
), f"OBX#1 performing_org should be 'ST JUDE MEDICAL CENTER', got {obxs[0].performing_org}"

# group_index should be 0 for flat array
assert (
    obxs[0].group_index == 0
), f"OBX#1 group_index should be 0, got {obxs[0].group_index}"

# ── Nested array-of-arrays test ──
NESTED_OBX_JSON = """[
  [{"0":"OBX","1":"1","2":"ST","3":"60573-3^Report template source^LN","5":"CAP Cancer Protocols","11":"F","14":"20250101120000"}],
  [],
  [{"0":"OBX","1":"1","2":"NM","3":"43798.100004300^Ki-67^CAPECC","5":"25","6":"^^UCUM","11":"F","14":"20250101120000","15":"SOME LAB^12345^CLIA"}]
]"""

nested_obxs = parse_obx_segments(NESTED_OBX_JSON)
assert (
    len(nested_obxs) == 2
), f"Nested: expected 2 segments (empty inner array skipped), got {len(nested_obxs)}"
assert (
    nested_obxs[0].group_index == 0
), f"First segment should be group 0, got {nested_obxs[0].group_index}"
assert (
    nested_obxs[1].group_index == 2
), f"Second segment should be group 2 (empty group 1 skipped), got {nested_obxs[1].group_index}"
assert (
    nested_obxs[1].performing_org == "SOME LAB"
), f"Nested OBX performing_org from field 15 should be 'SOME LAB', got {nested_obxs[1].performing_org}"
assert (
    nested_obxs[1].units == "^^UCUM"
), f"Nested OBX units should be '^^UCUM', got {nested_obxs[1].units}"
assert classify_obx(nested_obxs[0]) == "skip", "Nested: first OBX is metadata"
assert (
    classify_obx(nested_obxs[1]) == "measurement"
), "Nested: second OBX is NM measurement"

print("All assertions passed!")
