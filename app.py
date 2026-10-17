
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium

# ---------------------------------------------------------
# HEXAMINE - Mine Subsidence Monitoring Dashboard
# ---------------------------------------------------------
st.set_page_config(
    page_title="HEXAMINE Dashboard",
    page_icon="⛏️",
    layout="wide",
)

st.title("⛏️ HEXAMINE")
st.subheader("Mine Subsidence Monitoring Dashboard")
st.caption("Sensor data from ThingSpeak")

# ThingSpeak channel IDs
GROUND_CHANNEL = "3534817"
ENV_CHANNEL = "3534819"

GROUND_FIELDS = {
    "Temperature": "field1",
    "Humidity": "field2",
    "Vibration": "field3",
    "Crack Width": "field4",
    "X Axis": "field5",
    "Y Axis": "field6",
    "Displacement": "field7",
    "Rain": "field8",
}

ENV_FIELDS = {
    "Soil Moisture": "field1",
    "Risk Level": "field2",
}


def get_data(channel_id: str, api_key: str) -> pd.DataFrame:
    """Fetch recent readings from ThingSpeak."""
    url = f"https://api.thingspeak.com/channels/{channel_id}/feeds.json"

    try:
        response = requests.get(
            url,
            params={"api_key": api_key, "results": 100},
            timeout=15,
        )
        response.raise_for_status()
        feeds = response.json().get("feeds", [])
        return pd.DataFrame(feeds)

    except requests.RequestException as error:
        st.error(
            f"Could not fetch ThingSpeak channel "
            f"{channel_id}: {error}"
        )

    except ValueError:
        st.error(
            f"ThingSpeak returned invalid JSON for channel "
            f"{channel_id}."
        )

    return pd.DataFrame()


def latest_nonempty(frame: pd.DataFrame, field: str):
    """Get the latest non-empty field value."""
    if frame.empty or field not in frame.columns:
        return None

    values = frame[field].dropna()
    values = values[values.astype(str).str.strip() != ""]

    if values.empty:
        return None

    return values.iloc[-1]


def parse_risk_score(frame: pd.DataFrame):
    """Read numeric risk values between 0 and 100."""
    value = latest_nonempty(frame, ENV_FIELDS["Risk Level"])

    if value is None:
        return None, "No risk value"

    text_value = str(value).strip()

    try:
        score = float(text_value)

        if 0 <= score <= 100:
            if score < 35:
                return score, "LOW"
            elif score < 70:
                return score, "MEDIUM"
            else:
                return score, "HIGH"

        return None, f"Risk value outside 0-100: {text_value}"

    except (TypeError, ValueError):
        label = text_value.upper()

        if label in {"LOW", "MEDIUM", "HIGH"}:
            return None, label

        return None, f"Unrecognized risk value: {text_value}"


# ---------------------------------------------------------
# Read API keys from Streamlit secrets
# ---------------------------------------------------------
try:
    ground_key = st.secrets["GROUND_READ_KEY"]
    env_key = st.secrets["ENV_READ_KEY"]

except Exception:
    st.error(
        "ThingSpeak API keys were not found. Check "
        ".streamlit/secrets.toml for GROUND_READ_KEY "
        "and ENV_READ_KEY."
    )
    st.stop()


# ---------------------------------------------------------
# Fetch ThingSpeak data
# ---------------------------------------------------------
ground = get_data(GROUND_CHANNEL, ground_key)
environment = get_data(ENV_CHANNEL, env_key)

if ground.empty and environment.empty:
    st.warning(
        "No readings received. Check your Read API keys "
        "and confirm that both ThingSpeak channels contain data."
    )
    st.stop()


# Convert timestamps
for frame in (ground, environment):
    if not frame.empty and "created_at" in frame.columns:
        frame["created_at"] = pd.to_datetime(
            frame["created_at"],
            errors="coerce",
            utc=True,
        )

st.success("Dashboard connected to ThingSpeak.")


# ---------------------------------------------------------
# Latest sensor values
# ---------------------------------------------------------
left, right = st.columns(2)

with left:
    st.markdown("### Ground Monitoring")

    if ground.empty:
        st.info("Ground readings are not available.")

    else:
        latest_ground = ground.iloc[-1]
        metric_columns = st.columns(2)
        metric_index = 0

        for name, field in GROUND_FIELDS.items():
            value = latest_ground.get(field)

            if pd.notna(value) and str(value).strip():
                metric_columns[metric_index % 2].metric(
                    name, str(value)
                )
                metric_index += 1


with right:
    st.markdown("### Environment Monitoring")

    if environment.empty:
        st.info("Environment readings are not available.")

    else:
        latest_environment = environment.iloc[-1]
        metric_columns = st.columns(2)
        metric_index = 0

        for name, field in ENV_FIELDS.items():
            value = latest_environment.get(field)

            if pd.notna(value) and str(value).strip():
                metric_columns[metric_index % 2].metric(
                    name, str(value)
                )
                metric_index += 1


# ---------------------------------------------------------
# Mine risk gauge
# ---------------------------------------------------------
st.divider()
st.header("Mine Risk Indicator")

risk_score, risk_label = parse_risk_score(environment)

if risk_score is not None:

    gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=risk_score,
            number={"suffix": "/100"},
            title={"text": f"Risk Level: {risk_label}"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#303030"},
                "steps": [
                    {
                        "range": [0, 35],
                        "color": "#36A657",
                    },
                    {
                        "range": [35, 70],
                        "color": "#F4D03F",
                    },
                    {
                        "range": [70, 100],
                        "color": "#E53935",
                    },
                ],
            },
        )
    )

    gauge.update_layout(
        height=300,
        margin=dict(t=60, b=20, l=25, r=25),
    )

    st.plotly_chart(gauge, use_container_width=True)

    st.caption(
        "Prototype risk thresholds only. These values must be "
        "validated before any real mine-safety use."
    )

else:
    st.info(
        f"Latest ThingSpeak Risk Level: {risk_label}. "
        "A numeric gauge requires a value between 0 and 100."
    )


# ---------------------------------------------------------
# Ground sensor history charts
# ---------------------------------------------------------
st.divider()
st.header("Ground Sensor History")

if not ground.empty and "created_at" in ground.columns:

    for name, field in GROUND_FIELDS.items():

        if field in ground.columns:

            chart_data = ground[
                ["created_at", field]
            ].copy()

            chart_data[field] = pd.to_numeric(
                chart_data[field],
                errors="coerce",
            )

            chart_data = chart_data.dropna(
                subset=["created_at", field]
            )

            if not chart_data.empty:

                fig = px.line(
                    chart_data,
                    x="created_at",
                    y=field,
                    title=name,
                    markers=True,
                    labels={
                        "created_at": "Time",
                        field: name,
                    },
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True,
                )

else:
    st.info("Ground sensor history is not available.")


# ---------------------------------------------------------
# Environment history charts
# ---------------------------------------------------------
st.header("Environment History")

if not environment.empty and "created_at" in environment.columns:

    for name, field in ENV_FIELDS.items():

        if field in environment.columns:

            chart_data = environment[
                ["created_at", field]
            ].copy()

            chart_data[field] = pd.to_numeric(
                chart_data[field],
                errors="coerce",
            )

            chart_data = chart_data.dropna(
                subset=["created_at", field]
            )

            if not chart_data.empty:

                fig = px.line(
                    chart_data,
                    x="created_at",
                    y=field,
                    title=name,
                    markers=True,
                    labels={
                        "created_at": "Time",
                        field: name,
                    },
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True,
                )

else:
    st.info("Environment history is not available.")


# ---------------------------------------------------------
# Raw sensor readings
# ---------------------------------------------------------
with st.expander("View raw ground readings"):

    if not ground.empty:
        st.dataframe(
            ground,
            use_container_width=True,
        )
    else:
        st.info("No ground readings available.")


with st.expander("View raw environment readings"):

    if not environment.empty:
        st.dataframe(
            environment,
            use_container_width=True,
        )
    else:
        st.info("No environment readings available.")


# ---------------------------------------------------------
# X-axis and Y-axis sensor chart
# ---------------------------------------------------------
st.divider()
st.header("Sensor Axis Readings")

st.write(
    "X Axis and Y Axis are sensor readings, not GPS coordinates."
)

if not ground.empty and all(
    field in ground.columns for field in ("field5", "field6")
):

    axis_data = ground[["field5", "field6"]].copy()

    axis_data["field5"] = pd.to_numeric(
        axis_data["field5"],
        errors="coerce",
    )

    axis_data["field6"] = pd.to_numeric(
        axis_data["field6"],
        errors="coerce",
    )

    axis_data = axis_data.dropna(
        subset=["field5", "field6"]
    )

    if not axis_data.empty:

        latest_axis = axis_data.iloc[-1]

        col1, col2 = st.columns(2)

        col1.metric(
            "Latest X Axis Reading",
            f"{latest_axis['field5']:.3f}",
        )

        col2.metric(
            "Latest Y Axis Reading",
            f"{latest_axis['field6']:.3f}",
        )

        fig_xy = px.scatter(
            axis_data,
            x="field5",
            y="field6",
            title="X Axis vs Y Axis Sensor Readings",
            labels={
                "field5": "X Axis Reading",
                "field6": "Y Axis Reading",
            },
        )

        st.plotly_chart(
            fig_xy,
            use_container_width=True,
        )

    else:
        st.info("No numeric X/Y axis readings are available.")

else:
    st.info("X/Y axis fields are not available.")


# ---------------------------------------------------------
# Geographic risk-zone map
# ---------------------------------------------------------
st.divider()
st.header("HEXAMINE Geographic Risk-Zone Map")

st.warning(
    "The colored circles are illustrative only. They are not "
    "actual subsidence boundaries or measured risk zones."
)

st.write(
    "Enter the verified mine latitude and longitude below. "
    "Do not use the X Axis or Y Axis sensor readings as GPS coordinates."
)

with st.form("mine_map_form"):

    coord_col1, coord_col2 = st.columns(2)

    with coord_col1:
        mine_lat = st.number_input(
            "Mine latitude",
            min_value=-90.0,
            max_value=90.0,
            value=11.0,
            format="%.6f",
        )

    with coord_col2:
        mine_lon = st.number_input(
            "Mine longitude",
            min_value=-180.0,
            max_value=180.0,
            value=77.0,
            format="%.6f",
        )

    show_map = st.form_submit_button(
        "Show geographic risk map"
    )


if show_map:

    risk_map = folium.Map(
        location=[mine_lat, mine_lon],
        zoom_start=14,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    # Illustrative zones only
    folium.Circle(
        location=[mine_lat, mine_lon],
        radius=1000,
        color="#239B56",
        fill=True,
        fill_color="#239B56",
        fill_opacity=0.30,
        tooltip="Illustrative LOW-risk zone",
    ).add_to(risk_map)

    folium.Circle(
        location=[mine_lat, mine_lon],
        radius=600,
        color="#F1C40F",
        fill=True,
        fill_color="#F1C40F",
        fill_opacity=0.42,
        tooltip="Illustrative MEDIUM-risk zone",
    ).add_to(risk_map)

    folium.Circle(
        location=[mine_lat, mine_lon],
        radius=250,
        color="#E53935",
        fill=True,
        fill_color="#E53935",
        fill_opacity=0.50,
        tooltip="Illustrative HIGH-risk zone",
    ).add_to(risk_map)

    folium.Marker(
        [mine_lat, mine_lon],
        tooltip="Mine reference point",
        popup=(
            f"Reference point<br>"
            f"Latitude: {mine_lat}<br>"
            f"Longitude: {mine_lon}"
        ),
        icon=folium.Icon(
            color="blue",
            icon="info-sign",
        ),
    ).add_to(risk_map)

    folium.LayerControl().add_to(risk_map)

    st_folium(
        risk_map,
        height=550,
        use_container_width=True,
        returned_objects=[],
    )

else:
    st.info(
        "Enter verified mine coordinates and click "
        "'Show geographic risk map'."
    )


st.markdown(
    """
    **Risk-zone legend**

    🟢 Green — Low risk (illustrative)

    🟡 Yellow — Medium risk (illustrative)

    🔴 Red — High risk (illustrative)
    """
)


# ---------------------------------------------------------
# Schematic mine layout
# ---------------------------------------------------------
st.divider()
st.header("Schematic Mine Layout")

st.caption(
    "Illustrative tunnel layout only. Sensor locations and "
    "colors are examples and are not connected to real underground "
    "locations or measured risk."
)

fig_mine = go.Figure()

fig_mine.add_shape(
    type="rect",
    x0=0,
    y0=0,
    x1=10,
    y1=6,
    line=dict(color="gray", width=3),
    fillcolor="rgba(120,120,120,0.08)",
)

fig_mine.add_shape(
    type="line",
    x0=1,
    y0=3,
    x1=9,
    y1=3,
    line=dict(color="gray", width=12),
)

fig_mine.add_shape(
    type="line",
    x0=3,
    y0=1,
    x1=3,
    y1=5,
    line=dict(color="gray", width=10),
)

fig_mine.add_shape(
    type="line",
    x0=7,
    y0=1,
    x1=7,
    y1=5,
    line=dict(color="gray", width=10),
)

fig_mine.add_trace(
    go.Scatter(
        x=[1, 3, 5, 7, 9],
        y=[3, 4, 3, 2, 3],
        mode="markers+text",
        text=[
            "Sensor 1",
            "Sensor 2",
            "Sensor 3",
            "Sensor 4",
            "Sensor 5",
        ],
        textposition="top center",
        marker=dict(
            size=17,
            color=[
                "green",
                "green",
                "orange",
                "red",
                "green",
            ],
            line=dict(width=2, color="white"),
        ),
        name="Example sensors",
    )
)

fig_mine.update_layout(
    height=450,
    xaxis=dict(
        visible=False,
        range=[-0.5, 10.5],
    ),
    yaxis=dict(
        visible=False,
        range=[-0.5, 6.5],
        scaleanchor="x",
    ),
    showlegend=False,
    margin=dict(l=10, r=10, t=30, b=10),
)

st.plotly_chart(
    fig_mine,
    use_container_width=True,
)

st.caption(
    "Prototype dashboard only. It is not a certified mine-safety system."
)
