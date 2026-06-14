from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass

import plotly.graph_objects as go
from flask import Flask, Response, jsonify, render_template, request

from shared_inputs import read_shared_inputs, write_shared_inputs


app = Flask(__name__)

DEFAULT_INPUTS = {
    "production_amount": 1000.0,
    "useful_output": 850.0,
    "waste_generated": 150.0,
    "recovered_material": 120.0,
    "recycled_content": 40.0,
}

MONETARY_DEFAULTS = {
    "resale_value_per_tonne": 30000.0,
    "avoided_disposal_cost_per_tonne": 5000.0,
}

CHART_THEME = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "Inter", "color": "#596158", "size": 12},
    "title_font": {"family": "Space Grotesk", "color": "#101410", "size": 17},
    "colorway": ["#004d2d", "#d90f0f", "#0f8f56", "#8ef000"],
    "margin": {"t": 56, "b": 36, "l": 36, "r": 22},
}


@dataclass
class GapInputs:
    production_amount: float
    useful_output: float
    waste_generated: float
    recovered_material: float
    recycled_content: float


def parse_inputs(data: dict) -> GapInputs:
    values = DEFAULT_INPUTS.copy()
    values.update(data or {})

    def number(name: str, minimum: float = 0.0) -> float:
        try:
            parsed = float(values.get(name, DEFAULT_INPUTS[name]))
        except (TypeError, ValueError):
            parsed = float(DEFAULT_INPUTS[name])
        return max(minimum, parsed)

    return GapInputs(
        production_amount=number("production_amount", 1.0),
        useful_output=number("useful_output"),
        waste_generated=number("waste_generated"),
        recovered_material=number("recovered_material"),
        recycled_content=min(100.0, number("recycled_content")),
    )


def calculate_metrics(inputs: GapInputs) -> dict:
    resource_efficiency = (inputs.useful_output / inputs.production_amount) * 100

    if inputs.waste_generated > 0:
        recovery_potential = (inputs.recovered_material / inputs.waste_generated) * 100
    else:
        recovery_potential = 0

    waste_percentage = (inputs.waste_generated / inputs.production_amount) * 100
    recyclability_score = recovery_potential

    circularity_index = (
        resource_efficiency * 0.30
        + recovery_potential * 0.30
        + inputs.recycled_content * 0.25
        + (100 - waste_percentage) * 0.15
    )
    circularity_index = min(circularity_index, 100)
    circularity_gap = 100 - circularity_index

    return {
        "resource_efficiency": resource_efficiency,
        "recovery_potential": recovery_potential,
        "waste_percentage": waste_percentage,
        "recyclability_score": recyclability_score,
        "circularity_index": circularity_index,
        "circularity_gap": circularity_gap,
        "waste_reduction": 100 - waste_percentage,
    }


def status_for_index(circularity_index: float) -> dict:
    if circularity_index >= 85:
        return {"label": "Excellent Circularity Performance", "tone": "success"}
    if circularity_index >= 70:
        return {"label": "Good Circularity Performance", "tone": "info"}
    if circularity_index >= 50:
        return {"label": "Moderate Circularity Performance", "tone": "warning"}
    return {"label": "Low Circularity Performance", "tone": "danger"}


def recommendations(inputs: GapInputs, metrics: dict) -> list[str]:
    items = []

    if inputs.recycled_content < 50:
        items.append("Increase recycled material usage.")

    if metrics["recovery_potential"] < 70:
        items.append("Improve material recovery processes.")

    if metrics["resource_efficiency"] < 80:
        items.append("Reduce production losses.")

    if metrics["waste_percentage"] > 20:
        items.append("Implement waste reduction strategies.")

    if len(items) == 0:
        items.append("Current circularity performance is strong.")

    return items


def build_rows(inputs: GapInputs, metrics: dict) -> list[dict]:
    return [
        {"Metric": "Resource Efficiency", "Value (%)": round(metrics["resource_efficiency"], 2)},
        {"Metric": "Recovery Potential", "Value (%)": round(metrics["recovery_potential"], 2)},
        {"Metric": "Recycled Content", "Value (%)": round(inputs.recycled_content, 2)},
        {"Metric": "Waste Percentage", "Value (%)": round(metrics["waste_percentage"], 2)},
        {"Metric": "Circularity Index", "Value (%)": round(metrics["circularity_index"], 2)},
        {"Metric": "Circularity Gap", "Value (%)": round(metrics["circularity_gap"], 2)},
    ]


def apply_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(**CHART_THEME)
    fig.update_layout(autosize=True)
    return fig


def build_charts(inputs: GapInputs, metrics: dict) -> dict:
    gap_fig = go.Figure(
        go.Pie(
            labels=["Circularity Achieved", "Circularity Gap"],
            values=[metrics["circularity_index"], metrics["circularity_gap"]],
            hole=0.6,
            marker={"colors": ["#004d2d", "#d90f0f"]},
            textfont={"color": "#101410"},
            textposition="outside",
        )
    )
    gap_fig.update_layout(title="Circularity Performance")
    apply_theme(gap_fig)

    component_fig = go.Figure(
        go.Bar(
            x=[
                "Resource Efficiency",
                "Recovery Potential",
                "Recycled Content",
                "Waste Reduction",
            ],
            y=[
                metrics["resource_efficiency"],
                metrics["recovery_potential"],
                inputs.recycled_content,
                metrics["waste_reduction"],
            ],
            marker={
                "color": ["#004d2d", "#0f8f56", "#8ef000", "#b8d8c3"],
                "line": {"width": 0},
            },
            text=[
                f"{metrics['resource_efficiency']:.1f}%",
                f"{metrics['recovery_potential']:.1f}%",
                f"{inputs.recycled_content:.1f}%",
                f"{metrics['waste_reduction']:.1f}%",
            ],
            textposition="outside",
            textfont={"color": "#101410"},
        )
    )
    component_fig.update_layout(
        title="Component Contribution",
        xaxis={"showgrid": False, "color": "#596158"},
        yaxis={
            "range": [0, 115],
            "showgrid": True,
            "gridcolor": "#d4d6cf",
            "color": "#596158",
        },
    )
    apply_theme(component_fig)

    return {
        "gap": gap_fig.to_plotly_json(),
        "components": component_fig.to_plotly_json(),
    }


def build_payload(inputs: GapInputs) -> dict:
    metrics = calculate_metrics(inputs)
    return {
        "inputs": asdict(inputs),
        "metrics": metrics,
        "cards": {
            "circularity_index": f"{metrics['circularity_index']:.1f}%",
            "circularity_gap": f"{metrics['circularity_gap']:.1f}%",
            "recovery_potential": f"{metrics['recovery_potential']:.1f}%",
            "resource_efficiency": f"{metrics['resource_efficiency']:.1f}%",
        },
        "progress": {
            "value": round(metrics["circularity_index"], 2),
            "width": max(0, min(100, metrics["circularity_index"])),
        },
        "table": build_rows(inputs, metrics),
        "charts": build_charts(inputs, metrics),
        "status": status_for_index(metrics["circularity_index"]),
        "recommendations": recommendations(inputs, metrics),
    }


def parse_monetary_inputs(data: dict) -> tuple[GapInputs, dict]:
    inputs = parse_inputs(data)
    values = MONETARY_DEFAULTS.copy()
    values.update(data or {})

    def money(name: str) -> float:
        try:
            parsed = float(values.get(name, MONETARY_DEFAULTS[name]))
        except (TypeError, ValueError):
            parsed = MONETARY_DEFAULTS[name]
        return max(0.0, parsed)

    rates = {
        "resale_value_per_tonne": money("resale_value_per_tonne"),
        "avoided_disposal_cost_per_tonne": money("avoided_disposal_cost_per_tonne"),
    }
    rates["total_value_per_tonne"] = (
        rates["resale_value_per_tonne"] + rates["avoided_disposal_cost_per_tonne"]
    )
    return inputs, rates


def calculate_monetary_impact(inputs: GapInputs, rates: dict) -> dict:
    recovered_tonnes = inputs.recovered_material / 1000
    unrecovered_waste_kg = max(0, inputs.waste_generated - inputs.recovered_material)
    unrecovered_waste_tonnes = unrecovered_waste_kg / 1000

    current_value = recovered_tonnes * rates["total_value_per_tonne"]
    monetary_gap = unrecovered_waste_tonnes * rates["total_value_per_tonne"]
    total_opportunity = current_value + monetary_gap

    return {
        "recovered_tonnes": recovered_tonnes,
        "unrecovered_waste_kg": unrecovered_waste_kg,
        "unrecovered_waste_tonnes": unrecovered_waste_tonnes,
        "current_value": current_value,
        "monetary_gap": monetary_gap,
        "total_opportunity": total_opportunity,
    }


def build_monetary_chart(impact: dict) -> dict:
    fig = go.Figure(
        go.Bar(
            x=["Current Value", "Monetary Gap", "Total Opportunity"],
            y=[
                impact["current_value"],
                impact["monetary_gap"],
                impact["total_opportunity"],
            ],
            marker={
                "color": ["#004d2d", "#d90f0f", "#0f8f56"],
                "line": {"width": 0},
            },
            text=[
                f"₹{impact['current_value']:,.0f}",
                f"₹{impact['monetary_gap']:,.0f}",
                f"₹{impact['total_opportunity']:,.0f}",
            ],
            textposition="outside",
            textfont={"color": "#101410"},
        )
    )
    fig.update_layout(
        title="Circularity Value in Rupees",
        xaxis={"showgrid": False, "color": "#596158"},
        yaxis={"showgrid": True, "gridcolor": "#d4d6cf", "color": "#596158"},
        **CHART_THEME,
    )
    return fig.to_plotly_json()


def build_monetary_payload(data: dict) -> dict:
    inputs, rates = parse_monetary_inputs(data)
    circularity_metrics = calculate_metrics(inputs)
    impact = calculate_monetary_impact(inputs, rates)
    rows = [
        {"Metric": "Recovered Material (tonnes)", "Value": round(impact["recovered_tonnes"], 4)},
        {
            "Metric": "Unrecovered Waste (tonnes)",
            "Value": round(impact["unrecovered_waste_tonnes"], 4),
        },
        {
            "Metric": "Resale Value (₹/tonne)",
            "Value": round(rates["resale_value_per_tonne"], 2),
        },
        {
            "Metric": "Avoided Disposal Cost (₹/tonne)",
            "Value": round(rates["avoided_disposal_cost_per_tonne"], 2),
        },
        {
            "Metric": "Total Value Rate (₹/tonne)",
            "Value": round(rates["total_value_per_tonne"], 2),
        },
        {"Metric": "Current Monetary Value (₹)", "Value": round(impact["current_value"], 2)},
        {"Metric": "Monetary Gap (₹)", "Value": round(impact["monetary_gap"], 2)},
        {
            "Metric": "Total Monetary Opportunity (₹)",
            "Value": round(impact["total_opportunity"], 2),
        },
    ]
    return {
        "inputs": asdict(inputs),
        "rates": rates,
        "impact": impact,
        "circularity": {
            "index": round(circularity_metrics["circularity_index"], 2),
            "gap": round(circularity_metrics["circularity_gap"], 2),
            "recovery_potential": round(circularity_metrics["recovery_potential"], 2),
        },
        "cards": {
            "current_value": f"₹{impact['current_value']:,.0f}",
            "monetary_gap": f"₹{impact['monetary_gap']:,.0f}",
            "total_opportunity": f"₹{impact['total_opportunity']:,.0f}",
            "unrecovered_waste": f"{impact['unrecovered_waste_kg']:,.0f} kg",
        },
        "table": rows,
        "chart": build_monetary_chart(impact),
    }


def generate_csv(rows: list[dict]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["Metric", "Value (%)"])
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


@app.route("/")
def index():
    defaults = DEFAULT_INPUTS.copy()
    defaults.update(read_shared_inputs())
    return render_template("gap.html", defaults=defaults)


@app.route("/monetary")
def monetary():
    defaults = DEFAULT_INPUTS.copy()
    defaults.update(read_shared_inputs())
    defaults.update(MONETARY_DEFAULTS)
    return render_template("monetary.html", defaults=defaults)


@app.post("/api/calculate")
def api_calculate():
    inputs = parse_inputs(request.get_json(silent=True) or {})
    write_shared_inputs(asdict(inputs))
    return jsonify(build_payload(inputs))


@app.get("/api/shared")
def api_shared():
    return jsonify(read_shared_inputs())


@app.post("/api/monetary")
def api_monetary():
    data = request.get_json(silent=True) or {}
    inputs, _ = parse_monetary_inputs(data)
    write_shared_inputs(asdict(inputs))
    return jsonify(build_monetary_payload(data))


@app.get("/download")
def download_report():
    inputs = parse_inputs(request.args.to_dict())
    rows = build_rows(inputs, calculate_metrics(inputs))
    return Response(
        generate_csv(rows),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=circularity_report.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001, use_reloader=False)
