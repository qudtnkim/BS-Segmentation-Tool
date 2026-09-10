"""
Render Phase and Structure taxonomies as horizontal hierarchy trees.

Outputs:
    docs/phase_taxonomy.png
    docs/structure_taxonomy.png

Run from anywhere:
    python docs/draw_taxonomy.py
"""

from pathlib import Path
import matplotlib.pyplot as plt

OUT_DIR = Path(__file__).resolve().parent

PHASE = {
    "Om (Omentectomy)": [
        ("PO", "Partial Omentectomy"),
        ("TO", "Total Omentectomy"),
    ],
    "VL (Vessel Ligation)": [
        ("LGEV", "Left Gastro Epiploic Vessel Ligation"),
        ("RGEV", "Right Gastro Epiploic Vessel Ligation"),
        ("RGV", "Right Gastric Vessel Ligation"),
        ("LGV", "Left Gastric Vessel Ligation"),
        ("SGV", "Short Gastric Vessel Ligation"),
        ("PGV", "Posterior Gastric Vessel Ligation"),
        ("RCV", "Right Colic Vessel Ligation"),
        ("MCV", "Middle Colic Vessel Ligation"),
        ("ICVL", "Ileocolic Vessel Ligation"),
        ("RCVL", "Right Colic Vessel Ligation"),
        ("MCVL", "Middle Colic Vessel Ligation"),
        ("RBMCVL", "Middle Colic Vessel Right Branch Ligation"),
        ("LCVL", "Left Colic Vessel Ligation"),
        ("IMVL", "Inferior Mesenteric Vessel Ligation"),
        ("MRVL", "Middle Rectal Vessel Ligation"),
    ],
    "OT (Organ Transection)": [
        ("DT", "Duodenum Transection"),
        ("ST", "Stomach Transection"),
        ("ET", "Esophagus Transection"),
        ("JT", "Jejunum Transection"),
        ("CT", "Colon Transection"),
        ("IT", "Ileum Transection"),
        ("RT", "Rectum Transection"),
    ],
    "OR (Organ Reconstruction)": [
        ("GJ", "GastroJejunostomy"),
        ("GD", "GastroDuodenostomy"),
        ("EJ", "EsophagoJejunostomy"),
        ("JJ", "JejunoJejunostomy"),
        ("EG", "EsophagoGastrostomy"),
        ("IC", "Ileocolostomy"),
        ("CC", "Colocolostomy"),
        ("CR", "Colorectostomy"),
    ],
    "Etc (Miscellaneous)": [
        ("TP", "Trocar Placement"),
        ("PE", "Peritoneal Exploration"),
        ("WC", "Washing Cytology"),
        ("MDC", "Mesenteric Defect Closure"),
        ("LT", "Liver Traction"),
        ("GI", "Gauze Insertion"),
        ("GR", "Gauze Retrieval"),
        ("BC", "Bleeding Control"),
        ("Irr", "Irrigation"),
        ("SR", "Specimen Removal"),
        ("DI", "Drain Insertion"),
        ("DeID", "De-identification phase"),
        ("IRR-Ph", "Irrelevant phase"),
        ("CamClean", "Camera cleaning phase"),
    ],
    "LND (Lymph Node Dissection)": [
        ("1 LND", "Left paracardial LND"),
        ("2 LND", "Right paracardial LND"),
        ("3a LND", "Lesser curvature LND (3a)"),
        ("3b LND", "Lesser curvature LND (3b)"),
        ("4sa LND", "Left greater curv. LND (short gastric a.)"),
        ("4sb LND", "Left greater curv. LND (L gastroepiploic a.)"),
        ("4d LND", "Left greater curv. LND (R gastroepiploic a.)"),
        ("5 LND", "Supraduodenal LND"),
        ("6 LND", "Infrapyloric LND"),
        ("7 LND", "Left gastric LND"),
        ("8a LND", "Common hepatic LND (anterior)"),
        ("8p LND", "Common hepatic LND (posterior)"),
        ("9 LND", "Celiac LND"),
        ("10 LND", "Splenic hilar LND"),
        ("11p LND", "Proximal splenic LND"),
        ("11d LND", "Distal splenic LND"),
        ("12a LND", "Hepatoduodenal LND (12a)"),
        ("12b LND", "Hepatoduodenal LND (12b)"),
        ("12p LND", "Hepatoduodenal LND (12p)"),
        ("13 LND", "Post. surface of Pancreatic head LND"),
        ("14a LND", "Superior Mesenteric Artery LND"),
        ("14v LND", "Superior Mesenteric Vein LND"),
        ("15 LND", "Middle colic vessels LND"),
        ("16a1 LND", "Paraaortic LND (Diaphr. Aortic Hiatus)"),
        ("16a2 LND", "Paraaortic LND (Celiac a. - L renal v.)"),
        ("16b1 LND", "Paraaortic LND (L renal v. - IMA)"),
        ("16b2 LND", "Paraaortic LND (L renal v. - IMA)"),
    ],
}

STRUCTURE = {
    "Or (Organ)": [
        ("Sto", "Stomach"), ("Eso", "Esophagus"), ("Duo", "Duodenum"),
        ("SI", "Small Intestine"), ("Lv", "Liver"), ("Panc", "Pancreas"),
        ("Spl", "Spleen"), ("Col", "Colon"), ("Rec", "Rectum"),
        ("Mscol", "Mesocolon"), ("Gb", "Gallbladder"), ("Diap", "Diaphragm"),
        ("Crus", "Crus muscle"), ("Fal", "Falciform ligament"),
        ("Rlig", "Round ligament"), ("App", "Appendix"), ("Ut", "Uterus"),
        ("Ov", "Ovary"), ("Lu", "Lung"), ("H", "Heart"),
    ],
    "Art (Artery)": [
        ("CT", "Celiac trunk"), ("LGA", "Left gastric artery"),
        ("CHA", "Common hepatic artery"), ("RGA", "Right gastric artery"),
        ("PHA", "Proper hepatic artery"), ("RHA", "Right hepatic artery"),
        ("LHA", "Left hepatic artery"), ("GDA", "Gastroduodenal artery"),
        ("IPA", "Infrapyloric artery"), ("RGEA", "Right gastroepiploic artery"),
        ("ASPDA", "Ant. sup. pancreaticoduodenal artery"),
        ("SA", "Splenic artery"), ("LGEA", "Left gastroepiploic artery"),
        ("Ob LGEA", "Omental branch of L gastroepiploic a."),
        ("SGA", "Short gastric artery"), ("SMA", "Superior mesenteric artery"),
        ("ICA", "Ileo-colic artery"),
        ("RCA", "Right colic artery"), ("MCA", "Middle colic artery"),
        ("LCA", "Left colic artery"), ("IMA", "Inferior Mesenteric artery"),
        ("MA", "Marginal artery"), ("SRA", "Superior Rectal artery"),
        ("MRA", "Middle Rectal artery"),
    ],
    "V (Vein)": [
        ("LGV", "Left gastric vein"), ("SV", "Splenic vein"),
        ("PV", "Portal vein"), ("SMV", "Superior mesenteric vein"),
        ("GCT", "Gastrocolic trunk"), ("RGEV", "Right gastroepiploic vein"),
        ("ASPDV", "Ant. sup. pancreaticoduodenal vein"),
        ("ARCV", "Accessary right colic vein"),
        ("SGV", "Short gastric vein"), ("LGEV", "Left gastroepiploic vein"),
        ("RGV", "Right gastric vein"), ("ICV", "Ileo-colic vein"),
        ("RCV", "Right colic vein"), ("GCV", "Gastro colic vein"),
        ("MCV", "Middle colic vein"), ("LCV", "Left colic vein"),
        ("LHV", "Left hepatic vein"), ("RHV", "Right hepatic vein"),
        ("MHV", "Middle hepatic vein"), ("IVC", "Inferior Vena Cava"),
        ("IMV", "Inferior Mesenteric vein"), ("MV", "Marginal vein"),
        ("SRV", "Superior Rectal vein"), ("MRV", "Middle Rectal vein"),
    ],
    "LN (Lymph Node)": [
        ("1", "Left paracardial LN"),
        ("2", "Right paracardial LN"),
        ("3a", "Lesser curvature LN (3a)"),
        ("3b", "Lesser curvature LN (3b)"),
        ("4sa", "L greater curv. LN (short gastric a.)"),
        ("4sb", "L greater curv. LN (L gastroepiploic a.)"),
        ("4d", "L greater curv. LN (R gastroepiploic a.)"),
        ("5", "Supraduodenal LN"),
        ("6", "Infrapyloric LN"),
        ("7", "Left gastric LN"),
        ("8a", "Common hepatic LN (anterior)"),
        ("8p", "Common hepatic LN (posterior)"),
        ("9", "Celiac LN"),
        ("10", "Splenic hilar LN"),
        ("11p", "Proximal splenic LN"),
        ("11d", "Distal splenic LN"),
        ("12a", "Hepatoduodenal LN (12a)"),
        ("12b", "Hepatoduodenal LN (12b)"),
        ("12p", "Hepatoduodenal LN (12p)"),
        ("13", "Post. surface of Pancreatic head LN"),
        ("14a", "Superior Mesenteric Artery LN"),
        ("14v", "Superior Mesenteric Vein LN"),
        ("15", "Middle colic vessels LN"),
        ("16a1", "Paraaortic LN (Diaphr. Aortic Hiatus)"),
        ("16a2", "Paraaortic LN (Celiac a. - L renal v.)"),
        ("16b1", "Paraaortic LN (L renal v. - IMA)"),
        ("16b2", "Paraaortic LN (L renal v. - IMA)"),
    ],
    "N (Nerve)": [
        ("SHPN", "Superior hypogastric plexus"),
        ("HGN", "Hypogastric nerves"),
        ("PSN", "Pelvic splanchnic nerves"),
        ("AVN", "Anterior Vagus Nerve"),
        ("PVN", "Posterior Vagus Nerve"),
        ("HBV", "Hepatic branch of vagus"),
        ("CBV", "Celiac branch of vagus"),
        ("CP", "Celiac plexus"),
        ("AGB", "Anterior gastric branches"),
        ("PGB", "Posterior gastric branches"),
        ("ANL", "Anterior nerve of Latarjet"),
        ("PNL", "Posterior nerve of Latarjet"),
    ],
    "F (Fascia)": [
        ("MRF", "Mesorectal fascia"),
        ("PSF", "Presacral fascia"),
        ("WF", "Waldeyer's fascia"),
        ("DF", "Denonvilliers' fascia"),
        ("GF", "Gerota's fascia"),
        ("TF", "Toldt's fascia"),
        ("MF", "Mesocolic fascia"),
    ],
    "L (Ligament)": [
        ("HDL", "Hepatoduodenal ligament"),
        ("GHL", "Gastrohepatic ligament"),
        ("GPL", "Gastrophrenic ligament"),
        ("GSL", "Gastrosplenic ligament"),
        ("PEL", "Phrenoesophageal ligament"),
        ("SRL", "Splenorenal (lienorenal) ligament"),
        ("GCL", "Gastrocolic ligament"),
    ],
}


def draw_tree(taxonomy, title, out_path, root_color, cat_colors):
    total_leaves = sum(len(v) for v in taxonomy.values())
    row_h = 0.32
    fig_h = max(9, total_leaves * row_h + 1.5)
    fig_w = 16

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis("off")

    top = fig_h - 0.6
    bottom = 0.6
    y_positions = []
    n = total_leaves
    step = (top - bottom) / (n - 1) if n > 1 else 0
    for i in range(n):
        y_positions.append(top - i * step)

    root_x = 1.2
    cat_x = 4.5
    leaf_x = 8.0

    ax.text(root_x, fig_h / 2, "Root",
            ha="center", va="center", fontsize=13, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.5", fc=root_color, ec="black", lw=1.2))

    leaf_idx = 0
    for cat_i, (cat_name, subs) in enumerate(taxonomy.items()):
        color = cat_colors[cat_i % len(cat_colors)]
        first = leaf_idx
        last = leaf_idx + len(subs) - 1
        cat_y = (y_positions[first] + y_positions[last]) / 2

        ax.plot([root_x + 0.35, cat_x - 1.4], [fig_h / 2, cat_y],
                color="gray", lw=1.2, alpha=0.7, zorder=1)

        ax.text(cat_x, cat_y, cat_name,
                ha="center", va="center", fontsize=11, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.4", fc=color, ec="black", lw=1))

        for _, (abbr, full) in enumerate(subs):
            y = y_positions[leaf_idx]
            ax.plot([cat_x + 1.4, leaf_x - 0.05], [cat_y, y],
                    color=color, lw=0.8, alpha=0.55, zorder=1)
            ax.text(leaf_x, y, f"{abbr}",
                    ha="left", va="center", fontsize=9, fontweight="bold")
            ax.text(leaf_x + 1.55, y, f"— {full}",
                    ha="left", va="center", fontsize=8, color="#333")
            leaf_idx += 1

    ax.set_title(title, fontsize=15, fontweight="bold", pad=10)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[saved] {out_path}  ({total_leaves} leaves)")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n_phase = sum(len(v) for v in PHASE.values())
    n_struct = sum(len(v) for v in STRUCTURE.values())
    draw_tree(
        PHASE,
        f"Surgical Phase Taxonomy ({len(PHASE)} categories, {n_phase} sub-phases)",
        OUT_DIR / "phase_taxonomy.png",
        root_color="#fde68a",
        cat_colors=["#fcd34d", "#fca5a5", "#fdba74", "#a7f3d0", "#93c5fd", "#c4b5fd"],
    )
    draw_tree(
        STRUCTURE,
        f"Anatomical Structure Taxonomy ({len(STRUCTURE)} categories, {n_struct} sub-structures)",
        OUT_DIR / "structure_taxonomy.png",
        root_color="#fde68a",
        cat_colors=["#f9a8d4", "#fca5a5", "#93c5fd", "#fcd34d", "#a7f3d0", "#c4b5fd"],
    )


if __name__ == "__main__":
    main()
