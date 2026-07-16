"""
Streamlit Address Map

Install:
    pip install streamlit pandas openpyxl folium streamlit-folium geopy

Run:
    streamlit run streamlit_address_map.py

The uploaded Excel workbook should contain addresses in its first column.
A header row such as "Address" is optional.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Iterable

import folium
import pandas as pd
import streamlit as st
from folium.plugins import Fullscreen, MeasureControl, MousePosition
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium


APP_TITLE = "Address Rent Survey Map"
DEFAULT_AREA_SUFFIX = "Omaha, NE, USA"
HEADER_NAMES = {
    "address",
    "addresses",
    "location",
    "locations",
    "property address",
    "street address",
}


@dataclass(frozen=True)
class GeocodedAddress:
    address: str
    query: str
    latitude: float
    longitude: float
    matched_address: str


st.set_page_config(page_title=APP_TITLE, page_icon="🗺️", layout="wide")
st.title(APP_TITLE)
st.caption(
    "Upload an Excel file whose first column contains property addresses. "
    "The center address is shown as a star; uploaded addresses are shown as blue dots."
)


@st.cache_resource
def get_geocode_client():
    geolocator = Nominatim(
        user_agent="streamlit-address-rent-survey-map/1.0",
        timeout=20,
    )
    return RateLimiter(
        geolocator.geocode,
        min_delay_seconds=1.05,
        swallow_exceptions=True,
    )


@st.cache_data(show_spinner=False)
def geocode_query(query: str) -> tuple[float, float, str] | None:
    """Geocode one address and cache the result between Streamlit reruns."""
    location = get_geocode_client()(query, exactly_one=True)
    if location is None:
        return None

    return (
        float(location.latitude),
        float(location.longitude),
        str(location.address),
    )


def qualify_address(address: str, area_suffix: str) -> str:
    """Append the default area only when the address appears incomplete."""
    address = re.sub(r"\s+", " ", address).strip().strip(",")
    area_suffix = area_suffix.strip().strip(",")

    if not area_suffix:
        return address

    has_zip_code = bool(
        re.search(r"\b\d{5}(?:-\d{4})?\b", address)
    )

    has_city_and_state = bool(
        re.search(r",\s*[^,]+,\s*[A-Z]{2}\b", address, flags=re.IGNORECASE)
    )

    if has_zip_code or has_city_and_state:
        return address

    return f"{address}, {area_suffix}"


def geocode_with_fallbacks(address: str, area_suffix: str):
    base_query = qualify_address(address, area_suffix)

    queries = [
        base_query,
        base_query.replace(" Circle", " Cir"),
        base_query.replace(" S ", " South "),
        base_query.replace(" N ", " North "),
        base_query.replace(" N ", " North "),
        base_query.replace(" E ", " East "),
        base_query.replace(" W ", " West "),
        base_query.replace(" Boulevard ", " Blvd "),
        base_query.replace(" Street ", " Str "),
        base_query.replace(" Avenue ", " Ave "),
    ]

    if not re.search(r"\b\d{5}\b", base_query):
        queries.append(f"{base_query}")

    for query in dict.fromkeys(queries):
        result = geocode_query(query)

        if result is not None:
            latitude, longitude, matched_address = result

            return GeocodedAddress(
                address=address,
                query=query,
                latitude=latitude,
                longitude=longitude,
                matched_address=matched_address,
            )

    return None


def clean_address_values(values: Iterable[object]) -> list[str]:
    cleaned: list[str] = []

    for value in values:
        if pd.isna(value):
            continue

        address = re.sub(r"\s+", " ", str(value)).strip()
        if address:
            cleaned.append(address)

    if cleaned and cleaned[0].lower() in HEADER_NAMES:
        cleaned = cleaned[1:]

    seen: set[str] = set()
    unique: list[str] = []
    for address in cleaned:
        key = address.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(address)

    return unique


def read_excel_addresses(uploaded_file) -> list[str]:
    frame = pd.read_excel(
        uploaded_file,
        sheet_name=0,
        header=None,
        dtype=str,
        usecols=[0],
        engine="openpyxl",
    )
    return clean_address_values(frame.iloc[:, 0].tolist())


def geocode_addresses(
    addresses: list[str],
    area_suffix: str,
    progress_label: str,
    tuple[list[GeocodedAddress], list[str]]:
    successful: list[GeocodedAddress] = []
    failed: list[str] = []

    progress = st.progress(0, text=progress_label)
    total = max(len(addresses), 1)

    for index, address in enumerate(addresses, start=1):
        point = geocode_with_fallbacks(address, area_suffix)

        if point is None:
            failed.append(address)
        else:
            successful.append(point)

            progress.progress(
                index / total,
                text=f"{progress_label} ({index} of {len(addresses)})",
            )

        progress.empty()
    return successful, failed
)


def add_center_marker(
    map_object: folium.Map,
    point: GeocodedAddress,
    show_labels: bool,
) -> None:
    safe_address = html.escape(point.address)

    star_icon = folium.DivIcon(
        icon_size=(42, 42),
        icon_anchor=(21, 21),
        html=(
            '<div style="'
            "font-size:40px;"
            "line-height:40px;"
            "color:#d39b00;"
            "text-shadow:-1px -1px 0 #000,1px -1px 0 #000,"
            "-1px 1px 0 #000,1px 1px 0 #000;"
            '">★</div>'
        ),
    )

    folium.Marker(
        location=(point.latitude, point.longitude),
        icon=star_icon,
        popup=folium.Popup(
            f"<b>Center address</b><br>{safe_address}",
            max_width=350,
        ),
        tooltip=folium.Tooltip(
            f"<b>Center:</b> {safe_address}",
            permanent=show_labels,
            direction="right",
            offset=(20, 0),
            sticky=False,
        ),
        z_index_offset=1000,
    ).add_to(map_object)


def add_comparison_marker(
    map_object: folium.Map,
    point: GeocodedAddress,
    show_labels: bool,
) -> None:
    safe_address = html.escape(point.address)
    safe_match = html.escape(point.matched_address)

    folium.CircleMarker(
        location=(point.latitude, point.longitude),
        radius=7,
        color="#0b4fa2",
        weight=2,
        fill=True,
        fill_color="#2379d8",
        fill_opacity=0.95,
        popup=folium.Popup(
            (
                f"<b>{safe_address}</b><br>"
                f"<span style='font-size:11px'>Geocoder match: {safe_match}</span>"
            ),
            max_width=420,
        ),
        tooltip=folium.Tooltip(
            safe_address,
            permanent=show_labels,
            direction="right",
            offset=(9, 0),
            sticky=False,
        ),
    ).add_to(map_object)


def symmetric_bounds(
    center: GeocodedAddress,
    points: list[GeocodedAddress],
    padding_factor: float = 1.20,
) -> list[list[float]]:
    """Fit all points while keeping the starred address centered."""
    all_points = [center, *points]

    max_lat_delta = max(
        abs(point.latitude - center.latitude) for point in all_points
    )
    max_lon_delta = max(
        abs(point.longitude - center.longitude) for point in all_points
    )

    max_lat_delta = max(max_lat_delta, 0.004)
    max_lon_delta = max(max_lon_delta, 0.004)

    lat_delta = max_lat_delta * padding_factor
    lon_delta = max_lon_delta * padding_factor

    return [
        [center.latitude - lat_delta, center.longitude - lon_delta],
        [center.latitude + lat_delta, center.longitude + lon_delta],
    ]


def build_map(
    center: GeocodedAddress,
    comparison_points: list[GeocodedAddress],
    show_labels: bool,
    fit_all_points: bool,
    default_zoom: int,
) -> folium.Map:
    map_object = folium.Map(
        location=(center.latitude, center.longitude),
        zoom_start=default_zoom,
        tiles=None,
        control_scale=True,
        prefer_canvas=False,
    )

    folium.TileLayer(
        tiles="CartoDB positron",
        name="Light map",
        control=True,
        show=True,
    ).add_to(map_object)

    folium.TileLayer(
        tiles="OpenStreetMap",
        name="Street map",
        control=True,
        show=False,
    ).add_to(map_object)

    add_center_marker(map_object, center, show_labels)

    for point in comparison_points:
        add_comparison_marker(map_object, point, show_labels)

    Fullscreen(
        position="topright",
        title="Open full screen",
        title_cancel="Exit full screen",
        force_separate_button=True,
    ).add_to(map_object)

    MeasureControl(
        position="topright",
        primary_length_unit="feet",
        secondary_length_unit="miles",
        primary_area_unit="sqfeet",
        secondary_area_unit="acres",
    ).add_to(map_object)

    MousePosition(
        position="bottomleft",
        separator=", ",
        prefix="Coordinates:",
        num_digits=5,
    ).add_to(map_object)

    folium.LayerControl(collapsed=True).add_to(map_object)

    if fit_all_points and comparison_points:
        map_object.fit_bounds(
            symmetric_bounds(center, comparison_points),
            padding=(20, 20),
        )

    return map_object


def results_to_dataframe(
    center: GeocodedAddress,
    comparison_points: list[GeocodedAddress],
) -> pd.DataFrame:
    rows = [
        {
            "Marker Type": "Center",
            "Input Address": center.address,
            "Geocoding Query": center.query,
            "Matched Address": center.matched_address,
            "Latitude": center.latitude,
            "Longitude": center.longitude,
        }
    ]

    rows.extend(
        {
            "Marker Type": "Comparison",
            "Input Address": point.address,
            "Geocoding Query": point.query,
            "Matched Address": point.matched_address,
            "Latitude": point.latitude,
            "Longitude": point.longitude,
        }
        for point in comparison_points
    )

    return pd.DataFrame(rows)


with st.form("address_input_form"):
    center_address = st.text_input(
        "Center address",
        placeholder="Enter the address to appear as a gold star on the map",
        help="This address will appear as a gold star.",
    )

    uploaded_file = st.file_uploader(
        "Upload Excel address list",
        type=["xlsx"],
        help=(
            "Addresses must be in the first column of the first worksheet. "
            "A header such as 'Address' is optional."
        ),
    )

    area_suffix = st.text_input(
        "Default city/region for incomplete addresses",
        value=DEFAULT_AREA_SUFFIX,
        help=(
            "This is appended when an address does not already include the city. "
            "It is useful for entries such as '6942 N 97th Circle'."
        ),
    )

    submitted = st.form_submit_button(
        "Build map",
        type="primary",
        use_container_width=True,
    )


if submitted:
    if not center_address.strip():
        st.error("Enter a center address.")
    elif uploaded_file is None:
        st.error("Upload an Excel workbook.")
    else:
        try:
            uploaded_addresses = read_excel_addresses(uploaded_file)
        except Exception as exc:
            st.error(f"Could not read the Excel file: {exc}")
        else:
            if not uploaded_addresses:
                st.error("No addresses were found in the workbook's first column.")
            else:
                center_results, center_failures = geocode_addresses(
                    [center_address.strip()],
                    area_suffix,
                    "Geocoding center address",
                )

                if center_failures or not center_results:
                    st.error(
                        "The center address could not be located. "
                        "Add the city, state, and ZIP code, then try again."
                    )
                else:
                    comparison_points, failed_addresses = geocode_addresses(
                        uploaded_addresses,
                        area_suffix,
                        "Geocoding uploaded addresses",
                    )

                    st.session_state["map_center"] = center_results[0]
                    st.session_state["map_points"] = comparison_points
                    st.session_state["manual_points"] = []
                    st.session_state["failed_addresses"] = failed_addresses
                    st.session_state["manual_failed_addresses"] = []
                    st.session_state["uploaded_address_count"] = len(
                        uploaded_addresses
                    )


if "map_center" in st.session_state:
    center_point: GeocodedAddress = st.session_state["map_center"]
    excel_points: list[GeocodedAddress] = st.session_state["map_points"]
    manual_points: list[GeocodedAddress] = st.session_state.setdefault(
        "manual_points",
        [],
    )
    excel_failed_addresses: list[str] = st.session_state["failed_addresses"]
    manual_failed_addresses: list[str] = st.session_state.setdefault(
        "manual_failed_addresses",
        [],
    )
    uploaded_address_count: int = st.session_state["uploaded_address_count"]

    st.divider()
    st.subheader("Add locations after upload")
    st.caption(
        "Enter one address per line. New locations are added as blue points "
        "without requiring another Excel upload."
    )

    with st.form("add_locations_form", clear_on_submit=True):
        additional_address_text = st.text_area(
            "Additional addresses",
            placeholder=(
                "4614 S 140th Street, Omaha, NE 68137\n"
                "11529 Portal Road, La Vista, NE 68128"
            ),
            height=110,
        )
        add_locations_submitted = st.form_submit_button(
            "Add locations to map",
            type="primary",
            use_container_width=True,
        )

    if add_locations_submitted:
        new_addresses = clean_address_values(
            additional_address_text.splitlines()
        )

        if not new_addresses:
            st.warning("Enter at least one address to add.")
        else:
            existing_addresses = {
                center_point.address.casefold(),
                *(point.address.casefold() for point in excel_points),
                *(point.address.casefold() for point in manual_points),
            }

            addresses_to_add = [
                address
                for address in new_addresses
                if address.casefold() not in existing_addresses
            ]
            duplicate_count = len(new_addresses) - len(addresses_to_add)

            if not addresses_to_add:
                st.info("All entered addresses are already on the map.")
            else:
                added_points, newly_failed = geocode_addresses(
                    addresses_to_add,
                    area_suffix,
                    "Geocoding additional addresses",
                )

                st.session_state["manual_points"].extend(added_points)

                known_failed = {
                    address.casefold()
                    for address in st.session_state["manual_failed_addresses"]
                }
                st.session_state["manual_failed_addresses"].extend(
                    address
                    for address in newly_failed
                    if address.casefold() not in known_failed
                )

                if added_points:
                    st.success(
                        f"Added {len(added_points)} new location"
                        f"{'s' if len(added_points) != 1 else ''}."
                    )

                if duplicate_count:
                    st.info(
                        f"Skipped {duplicate_count} duplicate address"
                        f"{'es' if duplicate_count != 1 else ''}."
                    )

                if newly_failed:
                    st.warning(
                        f"Could not map {len(newly_failed)} entered address"
                        f"{'es' if len(newly_failed) != 1 else ''}."
                    )

    if st.session_state["manual_points"]:
        if st.button(
            "Clear manually added locations",
            use_container_width=True,
        ):
            st.session_state["manual_points"] = []
            st.session_state["manual_failed_addresses"] = []
            st.rerun()

    # Refresh local values after the add-location form updates session state.
    manual_points = st.session_state["manual_points"]
    manual_failed_addresses = st.session_state["manual_failed_addresses"]
    comparison_points = [*excel_points, *manual_points]
    failed_addresses = [
        *excel_failed_addresses,
        *manual_failed_addresses,
    ]

    st.divider()

    control_col_1, control_col_2, control_col_3 = st.columns(3)

    with control_col_1:
        show_labels = st.checkbox(
            "Always show address labels",
            value=True,
            help="Keep this enabled for a screenshot-ready map.",
        )

    with control_col_2:
        fit_all_points = st.checkbox(
            "Fit all points around center",
            value=True,
            help="Fits every point in view while keeping the star centered.",
        )

    with control_col_3:
        default_zoom = st.slider(
            "Initial zoom",
            min_value=4,
            max_value=19,
            value=12,
            disabled=fit_all_points,
        )

    map_object = build_map(
        center=center_point,
        comparison_points=comparison_points,
        show_labels=show_labels,
        fit_all_points=fit_all_points,
        default_zoom=default_zoom,
    )

    mapped_count = len(comparison_points)
    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric("Excel addresses", uploaded_address_count)
    metric_2.metric("Added manually", len(manual_points))
    metric_3.metric("Mapped blue points", mapped_count)
    metric_4.metric("Could not map", len(failed_addresses))

    try:
        st_folium(
            map_object,
            height=720,
            use_container_width=True,
            returned_objects=[],
            key="address_map",
        )
    except TypeError:
        st_folium(
            map_object,
            width=1200,
            height=720,
            returned_objects=[],
            key="address_map",
        )

    results_frame = results_to_dataframe(center_point, comparison_points)

    download_col, info_col = st.columns([1, 2])
    with download_col:
        st.download_button(
            "Download mapped coordinates",
            data=results_frame.to_csv(index=False).encode("utf-8"),
            file_name="mapped_addresses.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with info_col:
        st.caption(
            "For a clean screenshot, use the light map, leave labels enabled, "
            "then use the map's full-screen button."
        )

    with st.expander("Mapped-address details"):
        st.dataframe(results_frame, hide_index=True, use_container_width=True)

    if failed_addresses:
        with st.expander(
            f"Addresses that could not be mapped ({len(failed_addresses)})",
            expanded=True,
        ):
            st.warning(
                "Add a city, state, or ZIP code, then either enter the revised "
                "address above or upload a revised workbook."
            )
            st.dataframe(
                pd.DataFrame({"Unmapped Address": failed_addresses}),
                hide_index=True,
                use_container_width=True,
            )

st.caption(
    "Geocoding uses the public OpenStreetMap Nominatim service and is rate-limited. "
    "Previously geocoded addresses are cached."
)
