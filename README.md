# Address Rent Survey Map

A single-page Streamlit application that:

- centers an interactive map on a user-entered address;
- displays the center as a gold star;
- uploads addresses from the first column of an `.xlsx` workbook;
- displays uploaded addresses as blue points with labels;
- reports addresses that could not be geocoded; and
- downloads mapped coordinates as CSV.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy with Streamlit Community Cloud

1. Create a GitHub repository.
2. Upload `streamlit_app.py`, `requirements.txt`, `.gitignore`, and this `README.md`.
3. Sign in at https://share.streamlit.io using GitHub.
4. Click **Create app**.
5. Select the GitHub repository and the `main` branch.
6. Set the entrypoint to `streamlit_app.py`.
7. Choose Python 3.12 in Advanced settings.
8. Click **Deploy**.

## Excel format

Place addresses in the first column of the first worksheet. A header such as
`Address` is optional.

## Geocoding notice

This app uses the public OpenStreetMap Nominatim service and deliberately limits
requests to approximately one per second. It is suitable for light, user-triggered
use. For heavier or commercial use, replace Nominatim with a dedicated geocoding
provider and store the API key in Streamlit secrets.
