from __future__ import annotations

import csv
import io
import os
import textwrap
from datetime import datetime
from dataclasses import asdict, dataclass

import google.generativeai as genai
import plotly.graph_objects as go
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, send_from_directory

from shared_inputs import read_shared_inputs, write_shared_inputs


load_dotenv()

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "25"))

EMISSION_FACTORS = {
    "Electricity": 0.82,
    "Diesel": 2.68,
    "Truck Transport": 0.12,
    "Water": 0.0003,
}

METAL_PROFILES = {
    "Aluminium": {
        "source": "Residual alumina in red mud",
        "grade_percent": 9.3,
        "recovery_percent": 55,
        "energy_kwh_per_kg": 8.5,
        "water_l_per_kg": 18,
        "process_co2_kg_per_kg": 6.97,
    },
    "Steel": {
        "source": "Iron oxides converted to steel feed",
        "grade_percent": 22.7,
        "recovery_percent": 70,
        "energy_kwh_per_kg": 4.2,
        "water_l_per_kg": 12,
        "process_co2_kg_per_kg": 3.44,
    },
    "Copper": {
        "source": "Trace red-mud copper recovery",
        "grade_percent": 0.01,
        "recovery_percent": 35,
        "energy_kwh_per_kg": 18,
        "water_l_per_kg": 45,
        "process_co2_kg_per_kg": 14.76,
    },
    "Titanium": {
        "source": "Titanium dioxide minerals",
        "grade_percent": 4.5,
        "recovery_percent": 60,
        "energy_kwh_per_kg": 12,
        "water_l_per_kg": 30,
        "process_co2_kg_per_kg": 9.84,
    },
    "Iron": {
        "source": "Iron oxides in bauxite residue",
        "grade_percent": 22.7,
        "recovery_percent": 75,
        "energy_kwh_per_kg": 3.8,
        "water_l_per_kg": 10,
        "process_co2_kg_per_kg": 3.12,
    },
    "Scandium": {
        "source": "Trace scandium in bauxite residue",
        "grade_percent": 0.012,
        "recovery_percent": 65,
        "energy_kwh_per_kg": 85,
        "water_l_per_kg": 220,
        "process_co2_kg_per_kg": 69.7,
    },
    "Gallium": {
        "source": "Gallium associated with Bayer liquor/red mud streams",
        "grade_percent": 0.005,
        "recovery_percent": 15,
        "energy_kwh_per_kg": 60,
        "water_l_per_kg": 160,
        "process_co2_kg_per_kg": 49.2,
    },
    "Vanadium": {
        "source": "Trace vanadium in bauxite residue",
        "grade_percent": 0.06,
        "recovery_percent": 45,
        "energy_kwh_per_kg": 38,
        "water_l_per_kg": 95,
        "process_co2_kg_per_kg": 31.16,
    },
    "Yttrium": {
        "source": "Rare-earth-bearing red mud fraction",
        "grade_percent": 0.009,
        "recovery_percent": 50,
        "energy_kwh_per_kg": 72,
        "water_l_per_kg": 180,
        "process_co2_kg_per_kg": 59.04,
    },
    "Rare Earth Oxides": {
        "source": "Combined rare-earth oxide fraction",
        "grade_percent": 0.1,
        "recovery_percent": 55,
        "energy_kwh_per_kg": 48,
        "water_l_per_kg": 130,
        "process_co2_kg_per_kg": 39.36,
    },
}

CHART_THEME = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "Inter", "color": "#8b949e", "size": 12},
    "title_font": {"family": "Space Grotesk", "color": "#e6edf3", "size": 15},
    "colorway": ["#2ea04f", "#7ee8a2", "#388bfd", "#d29922", "#f78166"],
    "margin": {"t": 50, "b": 30, "l": 10, "r": 10},
}

DEFAULT_INPUTS = {
    "metal_type": "Aluminium",
    "production_amount": 1000.0,
    "electricity_used": 5000.0,
    "diesel_used": 200.0,
    "transport_distance": 300.0,
    "water_used": 10000.0,
    "waste_generated": 150.0,
    "recovered_material": 120.0,
    "useful_output": 850.0,
    "recycled_content": 40.0,
}

METAL_TYPES = list(METAL_PROFILES.keys())


@dataclass
class SustainabilityInputs:
    metal_type: str
    production_amount: float
    electricity_used: float
    diesel_used: float
    transport_distance: float
    water_used: float
    waste_generated: float
    recovered_material: float
    useful_output: float
    recycled_content: float


def parse_inputs(data: dict) -> SustainabilityInputs:
    values = DEFAULT_INPUTS.copy()
    values.update(data or {})

    metal_type = str(values.get("metal_type") or DEFAULT_INPUTS["metal_type"])
    if metal_type not in METAL_TYPES:
        metal_type = DEFAULT_INPUTS["metal_type"]

    def number(name: str, minimum: float = 0.0) -> float:
        try:
            parsed = float(values.get(name, DEFAULT_INPUTS[name]))
        except (TypeError, ValueError):
            parsed = float(DEFAULT_INPUTS[name])
        return max(minimum, parsed)

    return SustainabilityInputs(
        metal_type=metal_type,
        production_amount=number("production_amount", 1.0),
        electricity_used=number("electricity_used"),
        diesel_used=number("diesel_used"),
        transport_distance=number("transport_distance"),
        water_used=number("water_used"),
        waste_generated=number("waste_generated"),
        recovered_material=number("recovered_material"),
        useful_output=number("useful_output"),
        recycled_content=min(100.0, number("recycled_content")),
    )


def calculate_metrics(inputs: SustainabilityInputs) -> dict:
    metal_profile = METAL_PROFILES[inputs.metal_type]
    electricity_co2 = inputs.electricity_used * EMISSION_FACTORS["Electricity"]
    diesel_co2 = inputs.diesel_used * EMISSION_FACTORS["Diesel"]
    transport_co2 = (
        inputs.production_amount
        / 1000
        * inputs.transport_distance
        * EMISSION_FACTORS["Truck Transport"]
    )
    water_co2 = inputs.water_used * EMISSION_FACTORS["Water"]
    total_co2 = electricity_co2 + diesel_co2 + transport_co2 + water_co2

    diesel_energy = inputs.diesel_used * 10.7
    total_energy = inputs.electricity_used + diesel_energy

    waste_percentage = (inputs.waste_generated / inputs.production_amount) * 100
    resource_efficiency = (inputs.useful_output / inputs.production_amount) * 100
    recovery_potential = (
        inputs.recovered_material / inputs.waste_generated * 100
        if inputs.waste_generated > 0
        else 0
    )
    waste_score = max(0, 100 - waste_percentage)

    circularity_score = min(
        recovery_potential * 0.4
        + inputs.recycled_content * 0.3
        + resource_efficiency * 0.2
        + waste_score * 0.1,
        100,
    )

    grade_fraction = metal_profile["grade_percent"] / 100
    metal_recovery_fraction = metal_profile["recovery_percent"] / 100
    red_mud_feed_required = (
        inputs.production_amount / (grade_fraction * metal_recovery_fraction)
        if grade_fraction > 0 and metal_recovery_fraction > 0
        else 0
    )
    contained_metal = red_mud_feed_required * grade_fraction
    unrecovered_metal = max(0, contained_metal - inputs.production_amount)
    metal_energy = inputs.production_amount * metal_profile["energy_kwh_per_kg"]
    metal_water = inputs.production_amount * metal_profile["water_l_per_kg"]
    metal_process_co2 = inputs.production_amount * metal_profile["process_co2_kg_per_kg"]

    return {
        "electricity_co2": electricity_co2,
        "diesel_co2": diesel_co2,
        "transport_co2": transport_co2,
        "water_co2": water_co2,
        "total_co2": total_co2,
        "diesel_energy": diesel_energy,
        "total_energy": total_energy,
        "waste_percentage": waste_percentage,
        "resource_efficiency": resource_efficiency,
        "recovery_potential": recovery_potential,
        "waste_score": waste_score,
        "circularity_score": circularity_score,
        "metal_profile": metal_profile,
        "red_mud_feed_required": red_mud_feed_required,
        "contained_metal": contained_metal,
        "unrecovered_metal": unrecovered_metal,
        "metal_energy": metal_energy,
        "metal_water": metal_water,
        "metal_process_co2": metal_process_co2,
    }


def build_result_rows(inputs: SustainabilityInputs, metrics: dict) -> list[dict]:
    return [
        {"Metric": "Carbon Footprint (kg CO2)", "Value": round(metrics["total_co2"], 2)},
        {"Metric": "Total Energy (kWh)", "Value": round(metrics["total_energy"], 2)},
        {"Metric": "Water Consumption (L)", "Value": round(inputs.water_used, 2)},
        {"Metric": "Waste Generation (%)", "Value": round(metrics["waste_percentage"], 2)},
        {
            "Metric": "Resource Efficiency (%)",
            "Value": round(metrics["resource_efficiency"], 2),
        },
        {
            "Metric": "Recovery Potential (%)",
            "Value": round(metrics["recovery_potential"], 2),
        },
        {"Metric": "Circularity Score", "Value": round(metrics["circularity_score"], 2)},
        {"Metric": "Selected Metal", "Value": inputs.metal_type},
        {"Metric": "Red Mud Source", "Value": metrics["metal_profile"]["source"]},
        {
            "Metric": "Reference Red Mud Grade (%)",
            "Value": round(metrics["metal_profile"]["grade_percent"], 4),
        },
        {
            "Metric": "Metal Recovery Assumption (%)",
            "Value": round(metrics["metal_profile"]["recovery_percent"], 2),
        },
        {
            "Metric": "Estimated Red Mud Feed Required (kg)",
            "Value": round(metrics["red_mud_feed_required"], 2),
        },
        {
            "Metric": "Contained Metal in Feed (kg)",
            "Value": round(metrics["contained_metal"], 2),
        },
        {
            "Metric": "Unrecovered Metal in Residue (kg)",
            "Value": round(metrics["unrecovered_metal"], 2),
        },
        {
            "Metric": "Metal-Specific Energy Estimate (kWh)",
            "Value": round(metrics["metal_energy"], 2),
        },
        {
            "Metric": "Metal-Specific Water Estimate (L)",
            "Value": round(metrics["metal_water"], 2),
        },
        {
            "Metric": "Metal-Specific Process CO2 (kg)",
            "Value": round(metrics["metal_process_co2"], 2),
        },
    ]


def apply_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(**CHART_THEME)
    fig.update_layout(autosize=True)
    return fig


def build_charts(inputs: SustainabilityInputs, metrics: dict) -> dict:
    emission_fig = go.Figure(
        go.Pie(
            labels=["Electricity", "Diesel", "Transport", "Water"],
            values=[
                metrics["electricity_co2"],
                metrics["diesel_co2"],
                metrics["transport_co2"],
                metrics["water_co2"],
            ],
            hole=0.45,
            marker={"colors": ["#2ea04f", "#7ee8a2", "#388bfd", "#d29922"]},
            textfont={"color": "#e6edf3"},
            textposition="outside",
        )
    )
    emission_fig.update_layout(title="Carbon Emission Sources")
    apply_theme(emission_fig)

    performance_fig = go.Figure(
        go.Bar(
            x=[
                metrics["resource_efficiency"],
                metrics["recovery_potential"],
                metrics["circularity_score"],
                inputs.recycled_content,
            ],
            y=["Efficiency", "Recovery", "Circularity", "Recycled Content"],
            orientation="h",
            marker={
                "color": ["#2ea04f", "#7ee8a2", "#388bfd", "#d29922"],
                "line": {"width": 0},
            },
            text=[
                f"{metrics['resource_efficiency']:.1f}%",
                f"{metrics['recovery_potential']:.1f}%",
                f"{metrics['circularity_score']:.1f}%",
                f"{inputs.recycled_content:.1f}%",
            ],
            textposition="outside",
            textfont={"color": "#e6edf3", "size": 12},
        )
    )
    performance_fig.update_layout(
        title="Sustainability Performance (%)",
        xaxis={"range": [0, 115], "showgrid": False, "zeroline": False, "color": "#8b949e"},
        yaxis={"showgrid": False, "color": "#c9d1d9"},
    )
    apply_theme(performance_fig)

    material_fig = go.Figure(
        go.Bar(
            x=["Input", "Waste", "Recovered", "Output"],
            y=[
                inputs.production_amount,
                inputs.waste_generated,
                inputs.recovered_material,
                inputs.useful_output,
            ],
            marker={
                "color": ["#388bfd", "#f78166", "#d29922", "#2ea04f"],
                "line": {"width": 0},
            },
            text=[
                f"{inputs.production_amount:,.0f} kg",
                f"{inputs.waste_generated:,.0f} kg",
                f"{inputs.recovered_material:,.0f} kg",
                f"{inputs.useful_output:,.0f} kg",
            ],
            textposition="outside",
            textfont={"color": "#e6edf3"},
        )
    )
    material_fig.update_layout(
        title="Material Flow (kg)",
        xaxis={"showgrid": False, "color": "#8b949e"},
        yaxis={"showgrid": True, "gridcolor": "#21262d", "color": "#8b949e"},
    )
    apply_theme(material_fig)

    gauge_fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=metrics["circularity_score"],
            title={
                "text": "Circularity Score",
                "font": {"color": "#e6edf3", "family": "Space Grotesk", "size": 15},
            },
            number={
                "suffix": "/100",
                "font": {"color": "#7ee8a2", "size": 36, "family": "Space Grotesk"},
            },
            gauge={
                "axis": {
                    "range": [0, 100],
                    "tickcolor": "#8b949e",
                    "tickfont": {"color": "#8b949e"},
                },
                "bar": {"color": "#2ea04f"},
                "bgcolor": "#21262d",
                "bordercolor": "#30363d",
                "steps": [
                    {"range": [0, 40], "color": "#1c2128"},
                    {"range": [40, 70], "color": "#1a2f1e"},
                    {"range": [70, 100], "color": "#1f3d25"},
                ],
                "threshold": {
                    "line": {"color": "#7ee8a2", "width": 2},
                    "thickness": 0.75,
                    "value": 80,
                },
            },
        )
    )
    gauge_fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#8b949e"},
        margin={"t": 40, "b": 10},
    )

    return {
        "emissions": emission_fig.to_plotly_json(),
        "performance": performance_fig.to_plotly_json(),
        "material": material_fig.to_plotly_json(),
        "circularity": gauge_fig.to_plotly_json(),
    }


def build_payload(inputs: SustainabilityInputs) -> dict:
    metrics = calculate_metrics(inputs)
    return {
        "inputs": asdict(inputs),
        "metrics": metrics,
        "cards": {
            "total_co2": {"value": f"{metrics['total_co2']:,.1f}", "unit": "kg"},
            "total_energy": {"value": f"{metrics['total_energy']:,.0f}", "unit": "kWh"},
            "water_used": {"value": f"{inputs.water_used:,.0f}", "unit": "L"},
            "circularity_score": {
                "value": f"{metrics['circularity_score']:.1f}",
                "unit": "/ 100",
            },
            "red_mud_feed_required": {
                "value": f"{metrics['red_mud_feed_required']:,.0f}",
                "unit": "kg feed",
            },
            "metal_recovery": {
                "value": f"{metrics['metal_profile']['recovery_percent']:.0f}",
                "unit": "%",
            },
        },
        "table": build_result_rows(inputs, metrics),
        "charts": build_charts(inputs, metrics),
    }


def parse_comparison_inputs(data: dict) -> tuple[SustainabilityInputs, list[str]]:
    selected_metals = data.get("metals") or ["Aluminium", "Titanium"]
    selected_metals = [metal for metal in selected_metals if metal in METAL_TYPES]

    if len(selected_metals) < 2:
        selected_metals = ["Aluminium", "Titanium"]
    selected_metals = selected_metals[:3]

    base_inputs = parse_inputs({**data, "metal_type": selected_metals[0]})
    return base_inputs, selected_metals


def build_comparison_payload(data: dict) -> dict:
    base_inputs, selected_metals = parse_comparison_inputs(data)
    comparison_rows = []

    for metal in selected_metals:
        inputs = SustainabilityInputs(**{**asdict(base_inputs), "metal_type": metal})
        metrics = calculate_metrics(inputs)
        comparison_rows.append(
            {
                "metal": metal,
                "source": metrics["metal_profile"]["source"],
                "grade_percent": round(metrics["metal_profile"]["grade_percent"], 4),
                "recovery_percent": round(metrics["metal_profile"]["recovery_percent"], 2),
                "red_mud_feed_required": round(metrics["red_mud_feed_required"], 2),
                "total_energy": round(metrics["total_energy"], 2),
                "input_water": round(inputs.water_used, 2),
                "metal_energy": round(metrics["metal_energy"], 2),
                "metal_water": round(metrics["metal_water"], 2),
                "metal_process_co2": round(metrics["metal_process_co2"], 2),
                "total_co2": round(metrics["total_co2"], 2),
                "circularity_score": round(metrics["circularity_score"], 2),
            }
        )

    chart = go.Figure()
    chart_metrics = [
        ("Red Mud Feed (kg)", "red_mud_feed_required"),
        ("Operational CO2 (kg)", "total_co2"),
        ("Total Energy (kWh)", "total_energy"),
        ("Metal Energy (kWh)", "metal_energy"),
        ("Process CO2 (kg)", "metal_process_co2"),
    ]

    for label, key in chart_metrics:
        chart.add_trace(
            go.Bar(
                name=label,
                x=[row["metal"] for row in comparison_rows],
                y=[row[key] for row in comparison_rows],
                text=[f"{row[key]:,.0f}" for row in comparison_rows],
                textposition="outside",
            )
        )

    chart.update_layout(
        title="Metal Comparison",
        barmode="group",
        xaxis={"showgrid": False, "color": "#8b949e"},
        yaxis={"showgrid": True, "gridcolor": "#21262d", "color": "#8b949e"},
        **CHART_THEME,
    )

    return {
        "inputs": asdict(base_inputs),
        "metals": selected_metals,
        "rows": comparison_rows,
        "chart": chart.to_plotly_json(),
    }


def generate_csv(rows: list[dict]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["Metric", "Value"])
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _clean_pdf_text(value: object) -> str:
    text = str(value).replace("₹", "Rs.").replace("CO₂", "CO2")
    return text.encode("latin-1", "replace").decode("latin-1")


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_text_pdf(title: str, lines: list[str]) -> bytes:
    wrapped_lines = []
    for line in lines:
        if line == "":
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(textwrap.wrap(_clean_pdf_text(line), width=92) or [""])

    pages = []
    page_lines = []
    for line in wrapped_lines:
        page_lines.append(line)
        if len(page_lines) >= 38:
            pages.append(page_lines)
            page_lines = []
    if page_lines:
        pages.append(page_lines)

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    page_refs = []
    for index, page in enumerate(pages):
        page_obj_id = len(objects) + 1
        content_obj_id = len(objects) + 2
        page_refs.append(f"{page_obj_id} 0 R")

        stream_lines = ["BT", "/F1 10 Tf", "56 752 Td", f"({_pdf_escape(_clean_pdf_text(title))}) Tj"]
        stream_lines.extend(["/F1 9 Tf", "0 -28 Td"])
        for line in page:
            stream_lines.append(f"({_pdf_escape(line)}) Tj")
            stream_lines.append("0 -15 Td")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines)

        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_id} 0 R >>"
        )
        objects.append(f"<< /Length {len(stream.encode('latin-1', 'replace'))} >>\nstream\n{stream}\nendstream")

    objects[1] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>"

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{idx} 0 obj\n{obj}\nendobj\n".encode("latin-1", "replace"))

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
            "latin-1"
        )
    )
    return bytes(pdf)


def _section(lines: list[str], title: str) -> None:
    lines.extend(["", title, "-" * len(title)])


def _metric_rows(lines: list[str], rows: list[dict], value_key: str = "Value") -> None:
    for row in rows:
        lines.append(f"{row.get('Metric')}: {row.get(value_key)}")


def build_complete_report(data: dict) -> bytes:
    from gap import build_monetary_payload, build_payload as build_gap_payload, parse_inputs as parse_gap_inputs

    dashboard_inputs = data.get("dashboard") or DEFAULT_INPUTS.copy()
    comparison_inputs = data.get("comparison") or {
        **dashboard_inputs,
        "metals": ["Aluminium", "Titanium"],
    }
    gap_inputs = data.get("gap") or dashboard_inputs
    monetary_inputs = data.get("monetary") or gap_inputs
    gemini_insights = (data.get("gemini_insights") or "").strip()

    dashboard_payload = build_payload(parse_inputs(dashboard_inputs))
    comparison_payload = build_comparison_payload(comparison_inputs)
    gap_payload = build_gap_payload(parse_gap_inputs(gap_inputs))
    monetary_payload = build_monetary_payload(monetary_inputs)

    lines = [
        "Metalytics AI Complete Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]

    _section(lines, "Main Sustainability Dashboard")
    lines.append(f"Selected Metal: {dashboard_payload['inputs']['metal_type']}")
    _metric_rows(lines, dashboard_payload["table"])

    _section(lines, "Circularity Gap")
    _metric_rows(lines, gap_payload["table"], "Value (%)")
    lines.append(f"Status: {gap_payload['status']['label']}")
    lines.append("Recommendations:")
    for item in gap_payload["recommendations"]:
        lines.append(f"- {item}")

    _section(lines, "Metal Comparison")
    for row in comparison_payload["rows"]:
        lines.append(
            f"{row['metal']}: red mud feed {row['red_mud_feed_required']:,.2f} kg, "
            f"operational CO2 {row['total_co2']:,.2f} kg, total energy {row['total_energy']:,.2f} kWh, "
            f"process CO2 {row['metal_process_co2']:,.2f} kg, circularity {row['circularity_score']:.2f}"
        )

    _section(lines, "Monetary Impact")
    _metric_rows(lines, monetary_payload["table"])

    _section(lines, "Gemini AI Insights")
    if gemini_insights:
        for insight in gemini_insights.splitlines():
            if insight.strip():
                lines.append(insight.strip())
    else:
        lines.append("No Gemini insights were generated before export.")

    return build_text_pdf("Metalytics AI Complete Report", lines)


def get_gemini_insights(inputs: SustainabilityInputs, metrics: dict) -> str:
    prompt = f"""
You are a sustainability expert analyzing manufacturing data for a {inputs.metal_type} production facility.

Key sustainability metrics:
- Total CO2 Emissions: {metrics['total_co2']:.2f} kg
- Energy Consumption: {metrics['total_energy']:.2f} kWh
- Water Usage: {inputs.water_used:.0f} L
- Waste Generation: {metrics['waste_percentage']:.1f}% of production
- Resource Efficiency: {metrics['resource_efficiency']:.1f}%
- Material Recovery Rate: {metrics['recovery_potential']:.1f}%
- Circularity Score: {metrics['circularity_score']:.1f}/100
- Recycled Content: {inputs.recycled_content:.0f}%
- Red Mud Source Profile: {metrics['metal_profile']['source']}
- Reference Red Mud Grade: {metrics['metal_profile']['grade_percent']:.4f}%
- Estimated Red Mud Feed Required: {metrics['red_mud_feed_required']:.2f} kg
- Metal-Specific Energy Estimate: {metrics['metal_energy']:.2f} kWh
- Metal-Specific Process CO2 Estimate: {metrics['metal_process_co2']:.2f} kg

Provide 4-5 concise, actionable sustainability insights based specifically on these numbers.
Each insight must:
- Start with exactly one status word: Good, Warning, or Tip
- Be 1-2 sentences, specific to the actual values
- No bullet points, dashes, headers, or markdown
"""
    try:
        if not GEMINI_API_KEY:
            return "Warning Could not fetch Gemini insights: GEMINI_API_KEY or GOOGLE_API_KEY is not configured."
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            prompt,
            request_options={"timeout": GEMINI_TIMEOUT_SECONDS},
        )
        return response.text or "Warning Gemini returned an empty response."
    except Exception as exc:
        return f"Warning Could not fetch Gemini insights: {exc}"


@app.route("/")
def index():
    return render_template("landing.html")


@app.route("/dashboard")
def dashboard():
    defaults = DEFAULT_INPUTS.copy()
    defaults.update(read_shared_inputs())
    return render_template(
        "index.html",
        defaults=defaults,
        metal_types=METAL_TYPES,
    )


@app.get("/geomap")
def geomap_redirect():
    return redirect("/geomap/")


@app.get("/geomap/")
def geomap_index():
    return send_from_directory("GEOMAP", "index.html")


@app.get("/geomap/<path:filename>")
def geomap_assets(filename: str):
    return send_from_directory("GEOMAP", filename)


@app.route("/comparison")
def comparison():
    defaults = DEFAULT_INPUTS.copy()
    defaults.update(read_shared_inputs())
    return render_template(
        "comparison.html",
        defaults=defaults,
        metal_types=METAL_TYPES,
    )


@app.post("/api/calculate")
def api_calculate():
    inputs = parse_inputs(request.get_json(silent=True) or {})
    write_shared_inputs(asdict(inputs))
    return jsonify(build_payload(inputs))


@app.get("/api/shared")
def api_shared():
    return jsonify(read_shared_inputs())


@app.post("/api/compare")
def api_compare():
    data = request.get_json(silent=True) or {}
    base_inputs, _ = parse_comparison_inputs(data)
    write_shared_inputs(asdict(base_inputs))
    return jsonify(build_comparison_payload(data))


@app.post("/api/insights")
def api_insights():
    inputs = parse_inputs(request.get_json(silent=True) or {})
    metrics = calculate_metrics(inputs)
    insights = get_gemini_insights(inputs, metrics)
    return jsonify({"insights": insights})


@app.post("/api/export-report")
def api_export_report():
    pdf = build_complete_report(request.get_json(silent=True) or {})
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=sustainability_complete_report.pdf"},
    )


@app.get("/download")
def download_report():
    inputs = parse_inputs(request.args.to_dict())
    rows = build_result_rows(inputs, calculate_metrics(inputs))
    csv_text = generate_csv(rows)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=sustainability_report.csv",
        },
    )


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
