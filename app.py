import streamlit as st
from datetime import datetime, timedelta
import os

# -----------------------------------------------------------------------------
# 1. PAGE CONFIG & CUSTOM STYLING (NAVY THEME & SEAMLESS LOGO BLEND)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="VesselFlow",
    page_icon="⚓",
    layout="wide"
)

CUSTOM_CSS = """
<style>
    .stApp {
        background-color: #0B192C;
        color: #E2E8F0;
    }
    .stCard {
        background-color: #1E293B;
        padding: 1.25rem;
        border-radius: 0.5rem;
        border: 1px solid #334155;
        margin-bottom: 1rem;
    }
    .soft-alert {
        background-color: #713F12;
        color: #FEF08A;
        padding: 0.4rem 0.6rem;
        border-radius: 0.375rem;
        border-left: 4px solid #EAB308;
        margin-bottom: 0.4rem;
        font-size: 0.9rem;
        font-weight: 500;
    }
    .hard-alert {
        background-color: #7F1D1D;
        color: #FECACA;
        padding: 0.4rem 0.6rem;
        border-radius: 0.375rem;
        border-left: 4px solid #EF4444;
        margin-bottom: 0.4rem;
        font-size: 0.9rem;
        font-weight: 600;
    }
    h1, h2, h3, h4 {
        color: #F8FAFC !important;
    }
    [data-testid="stImage"] img {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    /* Fix expander header background and hover color to match Navy theme */
    [data-testid="stExpander"] summary {
        background-color: #1E293B !important;
        border: 1px solid #334155 !important;
        border-radius: 0.375rem !important;
    }
    [data-testid="stExpander"] summary:hover {
        background-color: #273548 !important;
        color: #F8FAFC !important;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Initialize session memory states
if "vessels" not in st.session_state:
    st.session_state.vessels = []

if "navigation" not in st.session_state:
    st.session_state.navigation = "dashboard"

if "selected_index" not in st.session_state:
    st.session_state.selected_index = None

if "show_new_form" not in st.session_state:
    st.session_state.show_new_form = False

if "show_handover" not in st.session_state:
    st.session_state.show_handover = False

# Helper: Auto-format raw numbers into MM/DD/YYYY HH:MM
def auto_format_datetime(val):
    if not val:
        return ""
    nums = "".join(filter(str.isdigit, val))
    if len(nums) >= 8:
        m, d, y, h, min_t = nums[0:2], nums[2:4], nums[4:8], nums[8:10], nums[10:12]
        formatted = f"{m}/{d}/{y}"
        if h:
            formatted += f" {h}"
            if min_t:
                formatted += f":{min_t}"
        return formatted
    return val

# Helper to parse stored date strings safely
def parse_dt(dt_str):
    if not dt_str or not isinstance(dt_str, str):
        return None
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y"):
        try:
            return datetime.strptime(dt_str.strip(), fmt)
        except ValueError:
            continue
    return None

# Helper to resolve inbound pilot time from Specific Time or Following Vessel
def get_inbound_pilot_target_dt(v):
    if v.get('following_vessel'):
        return parse_dt(v.get('following_movement_date', ''))
    else:
        return parse_dt(v.get('inbound_pilot_time', ''))

# Auto-compute status based on timestamps and pilot orders
def compute_vessel_status(v):
    now = datetime.now()
    
    atd_val = v.get('atd', '')
    if atd_val and atd_val.strip() and atd_val.upper() not in ["", "UNKNOWN", "TBD"]:
        return "Departed"
    
    dep_pilot_dt = parse_dt(v.get('departure_pilot_datetime', ''))
    if v.get('departure_pilot_ordered') and dep_pilot_dt and now >= dep_pilot_dt:
        return "Outbound"
    
    atb_val = v.get('atb', '')
    if atb_val and atb_val.strip() and atb_val.upper() not in ["", "UNKNOWN", "TBD"]:
        return "All Fast"
    
    ib_target_dt = get_inbound_pilot_target_dt(v)
    if v.get('inbound_ordered') and ib_target_dt and now >= ib_target_dt:
        ib_dest = v.get('inbound_dest', 'Berth')
        if ib_dest in ["Inshore Anchorage", "Layberth"]:
            if now >= ib_target_dt + timedelta(hours=5):
                return ib_dest
        return "Inbound"
    
    ata_val = v.get('ata', '')
    if ata_val and ata_val.strip() and ata_val.upper() not in ["", "UNKNOWN", "TBD"]:
        return "Arrived Offshore"

    return "Sailing to Port"

def get_current_status(v):
    override = v.get('status_override', 'Auto (Default)')
    if override and override != 'Auto (Default)':
        return override
    return compute_vessel_status(v)

# Determine bucket section for dashboard categorization
def get_vessel_bucket(v):
    atd_val = v.get('atd', '')
    is_departed = atd_val and atd_val.strip() and atd_val.upper() not in ["", "UNKNOWN", "TBD"]
    
    if is_departed:
        checklist_keys = [
            "enoa_filed", "form_3171", "tpe_called_in", "entrance_filed", 
            "cbp_payment_done", "clearance_filed", "receipt_sent", "bl_signed", 
            "sof_sent", "survey_sent", "spo_turned_in", "cbp_complete_turned_in", 
            "gate_list_submitted", "berth_app_submitted"
        ]
        all_checked = all(v.get(k, False) for k in checklist_keys)
        if all_checked:
            return "Sailed - Completed"
        else:
            return "Sailed - Action Needed"
            
    eta_dt = parse_dt(v.get('eta', ''))
    if eta_dt:
        days_to_eta = (eta_dt - datetime.now()).total_seconds() / 86400
        if days_to_eta <= 10:
            return "Sending Updates"
            
    return "Assigned"

# Single-line override helper for the dashboard schedule
def get_single_time_override(est, act, label):
    if act and act.strip() and act.upper() not in ["", "UNKNOWN", "TBD"]:
        actual_label = "AT" + label[2:] if label.startswith("ET") else "AT"
        return f"{actual_label}: {act}"
    if est and est.strip() and est.upper() not in ["", "UNKNOWN", "TBD"]:
        return f"{label}: {est}"
    return f"{label}: Unknown"

# -----------------------------------------------------------------------------
# 2. LOGIC ENGINE (v6.x COMPLIANCE ALERTS CALCULATOR)
# -----------------------------------------------------------------------------
def calculate_alerts(v):
    soft = []
    hard = []
    now = datetime.now()
    role = v.get("role", "")

    if not role:
        soft.append("Agency Role / Type is unselected.")

    eta_dt = parse_dt(v.get('eta', ''))
    etb_dt = parse_dt(v.get('etb', ''))
    etc_dt = parse_dt(v.get('etc', ''))
    etd_dt = parse_dt(v.get('etd', ''))
    atd_dt = parse_dt(v.get('atd', ''))

    # Sabine Pilots Daylight Restriction Engine
    def parse_numeric(val):
        if not val:
            return 0.0
        nums = "".join(c for c in str(val) if c.isdigit() or c == '.')
        try:
            return float(nums)
        except ValueError:
            return 0.0

    loa_val = parse_numeric(v.get('loa', ''))
    beam_val = parse_numeric(v.get('beam', ''))
    dwt_val = parse_numeric(v.get('deadweight', ''))
    dim_unit = v.get('dim_unit', 'Feet (ft)')

    # Normalize metrics to feet for uniform threshold comparison
    if "Meter" in dim_unit:
        loa_ft = loa_val * 3.28084
        beam_ft = beam_val * 3.28084
    else:
        loa_ft = loa_val
        beam_ft = beam_val

    # Sabine Pilots Criteria: >= 85,000 DWT, > 875 ft LOA, or > 125 ft Beam
    is_daylight_restricted = (dwt_val >= 85000 or loa_ft > 875 or beam_ft > 125)

    if is_daylight_restricted:
        def is_nighttime(dt_str):
            dt = parse_dt(dt_str)
            if dt:
                hour = dt.hour
                return hour < 6 or hour >= 18
            return False

        # Check Inbound / Berthing times
        if is_nighttime(v.get('inbound_pilot_time', '')) or is_nighttime(v.get('etb', '')):
            hard.append(f"Sabine Pilots Daylight Restriction (LOA: {loa_val}{'m' if 'Meter' in dim_unit else 'ft'}, Beam: {beam_val}, DWT: {dwt_val}): Inbound/Berthing scheduled during nighttime hours.")

        # Check Departure / ETD times
        if is_nighttime(v.get('departure_pilot_datetime', '')) or is_nighttime(v.get('etd', '')):
            hard.append(f"Sabine Pilots Daylight Restriction (LOA: {loa_val}{'m' if 'Meter' in dim_unit else 'ft'}, Beam: {beam_val}, DWT: {dwt_val}): Outbound/Departure scheduled during nighttime hours.")

    # eNOA: Only triggers if Full or Charterers/Cargo
    if eta_dt and role in ["Full", "Charterers/Cargo"]:
        hours_to_eta = (eta_dt - now).total_seconds() / 3600
        if hours_to_eta <= 96 and not v.get("enoa_filed"):
            hard.append("eNOA Not Filed (ETA <= 96h).")

    # 3171: Triggers for all except Protective
    if eta_dt and role != "Protective":
        hours_to_eta = (eta_dt - now).total_seconds() / 3600
        if hours_to_eta <= 96 and not v.get("form_3171"):
            hard.append("CBP Form 3171 Not Filed (ETA <= 96h).")

    # CBP TPE, Entrance, Payment, Clearance, Receipts: Exclude Owners/Husbandry and Protective
    if role not in ["Owners/Husbandry", "Protective"]:
        if v.get("inbound_ordered") and not v.get("tpe_called_in"):
            soft.append("TPE Call-In pending (Inbound pilot info entered).")
        active_st = get_current_status(v)
        if active_st == "Inbound" and not v.get("tpe_called_in"):
            hard.append("CBP TPE Call-In NOT checked while vessel is Inbound!")
        if eta_dt and eta_dt.weekday() in [5, 6] and now.weekday() >= 4 and not v.get("tpe_called_in"):
            hard.append("Weekend TPE Alert: Vessel arriving weekend & TPE not called in.")

        if active_st == "Inbound":
            soft.append("CBP Entrance Filing ready (Vessel under inbound pilot).")
        if active_st in ["All Fast", "Inshore Anchorage", "Layberth"]:
            if not v.get("entrance_filed"):
                hard.append("CBP Entrance Filing Required (Vessel berthed/anchored).")
            if not v.get("cbp_payment_done"):
                soft.append("CBP Payment pending post-berthing.")

        if v.get("entrance_filed") and not v.get("cbp_payment_done"):
            hard.append("CBP Entrance COMPLETE but Payment is NOT completed!")

        if v.get("cbp_payment_done"):
            if not v.get("clearance_filed"):
                soft.append("CBP Clearance Filing ready to be submitted.")
            if not v.get("receipt_sent"):
                soft.append("Port Clearance & Payment Receipt ready for Captain.")

        if etc_dt:
            hours_to_etc = (etc_dt - now).total_seconds() / 3600
            if hours_to_etc <= 12 and not v.get("clearance_filed"):
                hard.append("CBP Clearance Filing NOT submitted (ETC <= 12h).")

        if etd_dt:
            hours_to_etd = (etd_dt - now).total_seconds() / 3600
            if hours_to_etd <= 12 and not v.get("receipt_sent"):
                hard.append("Port Clearance & Receipt NOT sent to Captain (ETD <= 12h).")

        if atd_dt:
            hours_since_atd = (now - atd_dt).total_seconds() / 3600
            if not v.get("bl_signed"):
                soft.append("Bill of Lading (BL) pending sign/send.")
                if hours_since_atd >= 24:
                    hard.append("BL Signed & Sent OVERDUE (>= 24h since ATD).")

            if not v.get("cbp_complete_turned_in"):
                soft.append("CBP Complete package ready to turn in.")
                clr_dt = parse_dt(v.get("clearance_completed_time", ""))
                if clr_dt:
                    days_since_clearance = (now - clr_dt).days
                    if days_since_clearance >= 4:
                        hard.append("CBP Complete Package OVERDUE (>= 4 days since Clearance).")

    # General ATD Document Reminders
    if atd_dt:
        if not v.get("sof_sent"):
            hard.append("SOF NOT sent to Captain (ATD recorded).")
        if not v.get("survey_sent"):
            hard.append("Customer Survey NOT sent to Captain (ATD recorded).")

    active_st = get_current_status(v)
    if active_st in ["Outbound", "Departed"]:
        if not v.get("sof_sent"):
            soft.append("SOF ready to send to Captain.")
        if not v.get("survey_sent"):
            soft.append("Customer Survey ready to send to Captain.")

    if v.get("departure_pilot_ordered") and not v.get("spo_turned_in"):
        soft.append("SPO document turn-in pending.")

    # Pilot Orders & Gate Lists
    if not v.get("inbound_ordered"):
        if eta_dt and now >= eta_dt:
            soft.append("Inbound Pilots NOT ordered (Current time >= ETA).")
        if etb_dt and (etb_dt - now).total_seconds() / 3600 <= 24:
            hard.append("Inbound Pilots NOT ordered (ETB <= 24h).")

    if etc_dt:
        hours_to_etc = (etc_dt - now).total_seconds() / 3600
        if not v.get("departure_pilot_ordered"):
            if hours_to_etc <= 24:
                soft.append("Outbound Pilots NOT ordered (ETC <= 24h).")
            if hours_to_etc <= 12 and v.get("departure_order_type") != "Firm Order":
                hard.append("Outbound Pilots NOT ordered (ETC <= 12h).")
        if hours_to_etc <= 2 and not v.get("outbound_pilot_confirmed"):
            hard.append("URGENT: Outbound Pilots NOT confirmed (ETC <= 2h)!")

    if etb_dt and (etb_dt - now).total_seconds() / 3600 <= 24 and not v.get("gate_list_submitted"):
        if role in ["Full", "Owners/Husbandry"]:
            soft.append("Gate List submission recommended (ETB <= 24h).")

    # Gate List Inbound Subcheck (No hard alert if inbound to Layberth or Inshore Anchorage)
    if active_st == "Inbound" and not v.get("gate_list_submitted"):
        if role in ["Full", "Owners/Husbandry"]:
            ib_dest = v.get("inbound_dest", "")
            if ib_dest not in ["Layberth", "Inshore Anchorage"]:
                hard.append("Gate List NOT submitted while Vessel is Inbound!")

    # Berth App Check (Checks Terminal or Layberth name for Beaumont or Port Arthur)
    term_val = v.get("terminal", "")
    lay_val = v.get("layberth_name", "")
    if (any(p in term_val for p in ["Beaumont", "Port Arthur"]) or any(p in lay_val for p in ["Beaumont", "Port Arthur"])) and not v.get("berth_app_submitted"):
        hard.append("Port Authority Berth Application Required.")

    if v.get("coc_required") and not v.get("coc_complete"):
        if not v.get("coc_performance_driven") and eta_dt and (eta_dt - now).total_seconds() / 3600 <= 24:
            hard.append("USCG COC Exam details/data incomplete (ETA <= 24h).")

    return soft, hard
# -----------------------------------------------------------------------------
# 3. WEEKEND HANDOVER GENERATOR
# -----------------------------------------------------------------------------
def generate_handover_text(vessels):
    total = len(vessels)
    output = [f"Daniel Gher – Weekend Handover", f"Assigned Vessels: {total} //// Sending Updates: {total}\n"]
    
    for v in vessels:
        role_sys = f"{v.get('role', 'Unassigned')}"
        if v.get("call_type"):
            role_sys += f" ({v['call_type']})"
            
        output.append(f"**{v['name']} – {role_sys}**")
        
        active_st = get_current_status(v)
        status_info = f"Vessel is currently {active_st.lower()} at {v.get('terminal', 'Unknown Terminal')}."
        if v.get("etb"):
            status_info += f" ETB {v['etb']}."
        
        services = []
        if v.get("crew_change_notes") and v["crew_change_notes"] != "N/A":
            services.append(v["crew_change_notes"])
        if v.get("bunker_notes") and v["bunker_notes"] != "N/A":
            services.append(v["bunker_notes"])
        if v.get("package_notes") and v["package_notes"] != "None":
            services.append(f"Packages: {v['package_notes']}")
        if v.get("ctm_notes") and v["ctm_notes"] != "None":
            services.append(f"CTM: {v['ctm_notes']}")
            
        narrative = status_info + " " + " ".join(services)
        output.append(narrative.strip())
        
        output.append("Need to:")
        output.append("• Check emails")
        if v.get("call_type"):
            output.append(f"• Send updates in {v['call_type']}")
            
        soft_alerts, hard_alerts = calculate_alerts(v)
        for h in hard_alerts:
            output.append(f"• ACTION REQUIRED: {h}")
        for s in soft_alerts:
            output.append(f"• {s}")
            
        if v.get("custom_service_notes"):
            output.append(f"• {v['custom_service_notes']}")
            
        output.append("")
        
    return "\n".join(output)

# -----------------------------------------------------------------------------
# VIEW 1: VESSEL DETAIL PAGE (Full Info & Editing)
# -----------------------------------------------------------------------------
if st.session_state.navigation == "detail":
    idx = st.session_state.selected_index
    v = st.session_state.vessels[idx]
    
    col_nav1, col_nav2 = st.columns([6, 1])
    with col_nav1:
        if st.button("← Back to Dashboard"):
            st.session_state.navigation = "dashboard"
            st.rerun()
    with col_nav2:
        if st.button("🗑️ Delete Vessel", type="secondary"):
            st.session_state.vessels.pop(idx)
            st.session_state.navigation = "dashboard"
            st.success("Vessel deleted successfully.")
            st.rerun()
            
    st.write("---")
        
    st.title(f"Managing: {v['name']}")
    
    # SECTION 1: Agent Type & Type of Call
    with st.expander("👤 Agent Type & Call Type", expanded=True):
        roles_list = ["", "Full", "Owners/Husbandry", "Charterers/Cargo", "Protective"]
        current_role = v.get('role', '')
        selected_role = st.selectbox(
            "Agent Type",
            roles_list,
            index=roles_list.index(current_role) if current_role in roles_list else 0,
            key=f"sel_role_{idx}"
        )
        v['role'] = selected_role

        call_type_options = ["Fairwater", "S5"]
        if selected_role == "Full":
            call_type_options.append("Both")
        
        curr_call_type = v.get('call_type', 'Fairwater')
        if curr_call_type not in call_type_options:
            curr_call_type = "Fairwater"
            
        selected_call_type = st.selectbox("Type of Call", call_type_options, index=call_type_options.index(curr_call_type), key=f"sel_call_type_{idx}")
        v['call_type'] = selected_call_type
        
        if selected_call_type == "Both":
            pc1, pc2 = st.columns(2)
            with pc1:
                v['principal_fairwater'] = st.text_input("Fairwater Principal", value=v.get('principal_fairwater', ''), key=f"pf_{idx}")
            with pc2:
                v['principal_s5'] = st.text_input("S5 Principal", value=v.get('principal_s5', ''), key=f"ps5_{idx}")

        st.write("---")
        if v['role'] in ["Owners/Husbandry", "Full"]:
            v['owner_name'] = st.text_input("Owner Name", value=v.get('owner_name', ''), key=f"owner_{idx}")
        if v['role'] in ["Charterers/Cargo", "Full"]:
            v['charterer_name'] = st.text_input("Charterer Name", value=v.get('charterer_name', ''), key=f"charterer_{idx}")
        if v['role'] == "Protective":
            v['principal_name'] = st.text_input("Principal Name", value=v.get('principal_name', ''), key=f"principal_{idx}")

    # SECTION 2: Vessel Particulars (Editable Name & Details)
    with st.expander("📌 Vessel Particulars", expanded=True):
        v['name'] = st.text_input("Vessel Name", value=v.get('name', ''), key=f"vname_{idx}")
        
        # Unit toggle for LOA and Beam measurements
        unit_opts = ["Feet (ft)", "Meters (m)"]
        curr_unit = v.get('dim_unit', 'Feet (ft)')
        v['dim_unit'] = st.selectbox("Dimension Unit System", unit_opts, index=unit_opts.index(curr_unit) if curr_unit in unit_opts else 0, key=f"dim_unit_{idx}")

        col_a, col_b = st.columns(2)
        with col_a:
            v['imo'] = st.text_input("IMO Number", value=v.get('imo', ''), key=f"imo_{idx}")
            v['flag'] = st.text_input("Flag", value=v.get('flag', ''), key=f"flag_{idx}")
            v['call_sign'] = st.text_input("Call Sign", value=v.get('call_sign', ''), key=f"cs_{idx}")
        with col_b:
            v['loa'] = st.text_input(f"LOA ({'ft' if 'Feet' in v['dim_unit'] else 'm'})", value=v.get('loa', ''), key=f"loa_{idx}")
            v['beam'] = st.text_input(f"Beam ({'ft' if 'Feet' in v['dim_unit'] else 'm'})", value=v.get('beam', ''), key=f"beam_{idx}")
            v['deadweight'] = st.text_input("Deadweight (DWT)", value=v.get('deadweight', ''), key=f"dwt_{idx}")

    # SECTION 3: Voyage Information
    with st.expander("🗺️ Voyage Information", expanded=True):
        vi1, vi2 = st.columns(2)
        with vi1:
            v['voyage_number'] = st.text_input("Voyage Number", value=v.get('voyage_number', ''), key=f"vn_{idx}")
            v['coming_from'] = st.text_input("Coming From", value=v.get('coming_from', ''), key=f"cf_{idx}")
            v['next_port'] = st.text_input("Next Port", value=v.get('next_port', ''), key=f"np_{idx}")
        with vi2:
            st.write("") 
            st.write("") 
            v['inbound_draft'] = st.text_input("Inbound Deep Draft", value=v.get('inbound_draft', ''), key=f"idr_{idx}")
            v['outbound_draft'] = st.text_input("Departure Deep Draft", value=v.get('outbound_draft', ''), key=f"odr_{idx}")

    # SECTION 4: Terminal, Berth & Timestamps
    with st.expander("📍 Terminal, Berth & Timestamps", expanded=True):
        v['terminal'] = st.text_input("Terminal", value=v.get('terminal', ''), key=f"term_{idx}")
        v['dock'] = st.text_input("Dock / Berth", value=v.get('dock', ''), key=f"dock_{idx}")
            
        st.write("---")
        st.subheader("⏱️ Schedule & Port Call Timestamps (MM/DD/YYYY HH:MM)")
        
        t_col1, t_col2 = st.columns(2)
        with t_col1:
            st.markdown("### 📊 Estimated Times")
            v['eta'] = auto_format_datetime(st.text_input("ETA (Estimated Arrival)", value=v.get('eta', ''), key=f"sched_eta_{idx}"))
            v['etb'] = auto_format_datetime(st.text_input("ETB (Estimated Berthing)", value=v.get('etb', ''), key=f"sched_etb_{idx}"))
            v['etc'] = auto_format_datetime(st.text_input("ETC (Estimated Completion)", value=v.get('etc', ''), key=f"sched_etc_{idx}"))
            v['etd'] = auto_format_datetime(st.text_input("ETD (Estimated Departure)", value=v.get('etd', ''), key=f"sched_etd_{idx}"))
        with t_col2:
            st.markdown("### 📌 Actual Times")
            v['ata'] = auto_format_datetime(st.text_input("ATA (Actual Arrival)", value=v.get('ata', ''), key=f"sched_ata_{idx}"))
            v['atb'] = auto_format_datetime(st.text_input("ATB (Actual Berthing)", value=v.get('atb', ''), key=f"sched_atb_{idx}"))
            v['atc'] = auto_format_datetime(st.text_input("ATC (Actual Completion)", value=v.get('atc', ''), key=f"sched_atc_{idx}"))
            v['atd'] = auto_format_datetime(st.text_input("ATD (Actual Departure)", value=v.get('atd', ''), key=f"sched_atd_{idx}"))

    # SECTION 5: Tug & Pilots
    with st.expander("⚓ Tug & Pilots", expanded=True):
        tg1, tg2 = st.columns(2)
        with tg1:
            v['tug_company'] = st.selectbox("Tug Company", ["None", "Moran Towing", "Bay Towing"], index=["None", "Moran Towing", "Bay Towing"].index(v.get('tug_company', 'None')) if v.get('tug_company', 'None') in ["None", "Moran Towing", "Bay Towing"] else 0, key=f"tc_{idx}")
        with tg2:
            v['tug_billing'] = st.selectbox("Tug Billing Type", ["Nominated", "Direct Bill"], index=0 if v.get('tug_billing', 'Nominated') == 'Nominated' else 1, key=f"tb_{idx}")
            
        st.write("---")
        st.subheader("Pilot Orders & Routing")

        st.markdown("### Inbound Pilots")
        v['inbound_ordered'] = st.checkbox("Inbound Pilots Ordered", value=v.get('inbound_ordered', False), key=f"in_ord_{idx}")
        
        if v['inbound_ordered']:
            ib_dest_options = ["Berth", "Layberth", "Inshore Anchorage"]
            curr_ib_dest = v.get('inbound_dest', 'Berth')
            v['inbound_dest'] = st.selectbox("Destination", ib_dest_options, index=ib_dest_options.index(curr_ib_dest) if curr_ib_dest in ib_dest_options else 0, key=f"ib_dest_sel_{idx}")

            if v['inbound_dest'] == "Berth":
                ib_basis = st.radio("Order Basis", ["Specific Time", "Following Vessel"], index=0 if v.get('ib_basis', 'Specific Time') == 'Specific Time' else 1, key=f"ib_basis_berth_{idx}")
                v['ib_basis'] = ib_basis
                if ib_basis == "Specific Time":
                    v['inbound_pilot_time'] = auto_format_datetime(st.text_input("Order Date and Time", value=v.get('inbound_pilot_time', ''), key=f"ib_p_time_{idx}", placeholder="MM/DD/YYYY HH:MM"))
                    v['following_vessel'] = False
                    v['following_vessel_name'] = ""
                    v['following_movement_date'] = ""
                else:
                    v['following_vessel'] = True
                    v['following_vessel_name'] = st.text_input("Name of Vessel Being Followed", value=v.get('following_vessel_name', ''), key=f"fol_name_{idx}")
                    v['following_movement_date'] = auto_format_datetime(st.text_input("Date for Movement (Links to Status Arrived Offshore -> Inbound)", value=v.get('following_movement_date', ''), key=f"fol_mov_dt_{idx}", placeholder="MM/DD/YYYY HH:MM"))
                    v['inbound_pilot_time'] = ""
            elif v['inbound_dest'] == "Layberth":
                lb_by_opts = ["Terminal", "Owners/Charterers"]
                curr_lb_by = v.get('layberth_ordered_by', 'Terminal')
                v['layberth_ordered_by'] = st.selectbox("Ordered By", lb_by_opts, index=lb_by_opts.index(curr_lb_by) if curr_lb_by in lb_by_opts else 0, key=f"lb_by_{idx}")
                v['layberth_name'] = st.text_input("Layberth Name", value=v.get('layberth_name', ''), key=f"lb_name_{idx}")
                if v['layberth_ordered_by'] == "Owners/Charterers":
                    v['layberth_reason'] = st.text_input("Reason (bunkers, exam, survey, etc.)", value=v.get('layberth_reason', ''), key=f"lb_reason_{idx}")
                else:
                    v['layberth_reason'] = "Pre-Stage"
                
                ib_basis = st.radio("Order Basis", ["Specific Time", "Following Vessel"], index=0 if v.get('ib_basis_lb', 'Specific Time') == 'Specific Time' else 1, key=f"ib_basis_lb_{idx}")
                v['ib_basis'] = ib_basis
                if ib_basis == "Specific Time":
                    v['inbound_pilot_time'] = auto_format_datetime(st.text_input("Order Date and Time", value=v.get('inbound_pilot_time', ''), key=f"ib_p_time_lb_{idx}", placeholder="MM/DD/YYYY HH:MM"))
                    v['following_vessel'] = False
                    v['following_vessel_name'] = ""
                    v['following_movement_date'] = ""
                else:
                    v['following_vessel'] = True
                    v['following_vessel_name'] = st.text_input("Name of Vessel Being Followed", value=v.get('following_vessel_name', ''), key=f"fol_name_lb_{idx}")
                    v['following_movement_date'] = auto_format_datetime(st.text_input("Date for Movement (Links to Status Arrived Offshore -> Inbound)", value=v.get('following_movement_date', ''), key=f"fol_mov_dt_lb_{idx}", placeholder="MM/DD/YYYY HH:MM"))
                    v['inbound_pilot_time'] = ""
            elif v['inbound_dest'] == "Inshore Anchorage":
                v['anchorage_name'] = st.text_input("Anchorage Name / Location", value=v.get('anchorage_name', ''), key=f"anc_name_{idx}")
                v['anchorage_reason'] = st.text_input("Reason for Anchorage (bunkers, exam, survey, etc.)", value=v.get('anchorage_reason', ''), key=f"anc_reason_{idx}")
                
                ib_basis = st.radio("Order Basis", ["Specific Time", "Following Vessel"], index=0 if v.get('ib_basis_anc', 'Specific Time') == 'Specific Time' else 1, key=f"ib_basis_anc_{idx}")
                v['ib_basis'] = ib_basis
                if ib_basis == "Specific Time":
                    v['inbound_pilot_time'] = auto_format_datetime(st.text_input("Order Date and Time", value=v.get('inbound_pilot_time', ''), key=f"ib_p_time_anc_{idx}", placeholder="MM/DD/YYYY HH:MM"))
                    v['following_vessel'] = False
                    v['following_vessel_name'] = ""
                    v['following_movement_date'] = ""
                else:
                    v['following_vessel'] = True
                    v['following_vessel_name'] = st.text_input("Name of Vessel Being Followed", value=v.get('following_vessel_name', ''), key=f"fol_name_anc_{idx}")
                    v['following_movement_date'] = auto_format_datetime(st.text_input("Date for Movement (Links to Status Arrived Offshore -> Inbound)", value=v.get('following_movement_date', ''), key=f"fol_mov_dt_anc_{idx}", placeholder="MM/DD/YYYY HH:MM"))
                    v['inbound_pilot_time'] = ""

        show_shifting = v.get('inbound_ordered', False) and v.get('inbound_dest', '') in ["Layberth", "Inshore Anchorage"]

        if show_shifting:
            st.write("---")
            st.markdown("### Shifting Pilots")
            v['shifting_ordered'] = st.checkbox("Shifting Pilots Ordered", value=v.get('shifting_ordered', False), key=f"sh_ord_{idx}")
            
            if v['shifting_ordered']:
                v['shifting_dest'] = st.text_input("Shifting Destination (e.g. Berth)", value=v.get('shifting_dest', ''), key=f"sh_dest_{idx}")
                sh_basis = st.radio("Shift Order Basis", ["Specific Time", "Following Vessel"], index=0 if v.get('sh_basis', 'Specific Time') == 'Specific Time' else 1, key=f"sh_basis_{idx}")
                v['sh_basis'] = sh_basis
                if sh_basis == "Specific Time":
                    v['shifting_pilot_time'] = auto_format_datetime(st.text_input("Shift Order Date and Time", value=v.get('shifting_pilot_time', ''), key=f"sh_p_time_{idx}", placeholder="MM/DD/YYYY HH:MM"))
                else:
                    v['shifting_following_name'] = st.text_input("Name of Vessel Being Followed (Shift)", value=v.get('shifting_following_name', ''), key=f"sh_fol_name_{idx}")

        st.write("---")
        st.markdown("### Departure Pilots")
        v['departure_pilot_ordered'] = st.checkbox("Departure Pilots Ordered", value=v.get('departure_pilot_ordered', False), key=f"dep_ord_{idx}")
        
        if v['departure_pilot_ordered']:
            dep_type_opts = ["Estimate Order", "Firm Order"]
            curr_dep_type = v.get('departure_order_type', 'Estimate Order')
            v['departure_order_type'] = st.selectbox("Order Type", dep_type_opts, index=dep_type_opts.index(curr_dep_type) if curr_dep_type in dep_type_opts else 0, key=f"dep_type_sel_{idx}")
            v['departure_pilot_datetime'] = auto_format_datetime(st.text_input("Date and Time for Order", value=v.get('departure_pilot_datetime', ''), key=f"dep_dt_{idx}", placeholder="MM/DD/YYYY HH:MM"))

        st.write("---")
        auto_status = compute_vessel_status(v)
        status_options = [
            "Auto (Default)",
            "Sailing to Port",
            "Arrived Offshore",
            "Inbound",
            "Inshore Anchorage",
            "Layberth",
            "All Fast",
            "Outbound",
            "Departed"
        ]
        curr_override = v.get('status_override', 'Auto (Default)')
        
        sc1, sc2 = st.columns(2)
        with sc1:
            st.write(f"**Auto-Calculated Status:** {auto_status}")
        with sc2:
            v['status_override'] = st.selectbox("Manual Status Override", status_options, index=status_options.index(curr_override) if curr_override in status_options else 0, key=f"stat_ov_{idx}")

    # SECTION 6: Port Services & Vendors
    with st.expander("🛠️ Port Services & Vendors", expanded=True):
        
        # 1. Crew Change
        v["crew_change_enabled"] = st.checkbox("Crew Change", value=v.get("crew_change_enabled", False), key=f"cc_en_{idx}")
        if v["crew_change_enabled"]:
            if "crew_members" not in v:
                v["crew_members"] = [{"rank": "", "name": "", "flight": ""}]
            
            st.markdown("##### Crew Members Listing")
            for c_idx, member in enumerate(v.get("crew_members", [])):
                rc1, rc2, rc3, rc4 = st.columns([1.5, 2, 2, 0.6])
                with rc1:
                    member["rank"] = st.text_input(f"Rank {c_idx+1}", value=member.get("rank", ""), key=f"cr_rank_{idx}_{c_idx}")
                with rc2:
                    member["name"] = st.text_input(f"Name {c_idx+1}", value=member.get("name", ""), key=f"cr_name_{idx}_{c_idx}")
                with rc3:
                    member["flight"] = st.text_input(f"Flight Details {c_idx+1}", value=member.get("flight", ""), key=f"cr_flight_{idx}_{c_idx}")
                with rc4:
                    st.write("")
                    st.write("")
                    if st.button("❌", key=f"del_crew_{idx}_{c_idx}"):
                        v["crew_members"].pop(c_idx)
                        st.rerun()
            
            if st.button("➕ Add Crewman", key=f"add_crew_{idx}"):
                v["crew_members"].append({"rank": "", "name": "", "flight": ""})
                st.rerun()
            
            v["crew_change_notes"] = st.text_input("Additional Crew Change Notes", value=v.get("crew_change_notes", ""), key=f"cc_notes_{idx}")

        st.divider()

        # 2. Bunkers
        v["bunker_enabled"] = st.checkbox("Bunkers", value=v.get("bunker_enabled", False), key=f"bk_en_{idx}")
        if v["bunker_enabled"]:
            bc_1, bc_2 = st.columns(2)
            with bc_1:
                v["bunker_supplier"] = st.text_input("Supplier Name", value=v.get("bunker_supplier", ""), key=f"bk_supp_{idx}")
            with bc_2:
                v["bunker_tug_barge"] = st.text_input("Tug/Barge Name", value=v.get("bunker_tug_barge", ""), key=f"bk_tb_{idx}")

            if "bunker_nom_list" not in v:
                v["bunker_nom_list"] = [{"type": "", "qty": ""}]
            st.markdown("##### Nominated Quantities")
            for b_i, b_item in enumerate(v["bunker_nom_list"]):
                bnc1, bnc2, bnc3 = st.columns([2, 2, 0.6])
                with bnc1:
                    b_item["type"] = st.text_input(f"Type (Nom) {b_i+1}", value=b_item.get("type",""), key=f"bn_t_{idx}_{b_i}")
                with bnc2:
                    b_item["qty"] = st.text_input(f"Quantity (Nom) {b_i+1}", value=b_item.get("qty",""), key=f"bn_q_{idx}_{b_i}")
                with bnc3:
                    st.write(""); st.write("")
                    if st.button("❌", key=f"del_bn_{idx}_{b_i}"):
                        v["bunker_nom_list"].pop(b_i); st.rerun()
            if st.button("➕ Add Nominated Bunker", key=f"add_bn_{idx}"):
                v["bunker_nom_list"].append({"type": "", "qty": ""}); st.rerun()

            if "bunker_act_list" not in v:
                v["bunker_act_list"] = [{"qty": "", "type": ""}]
            st.markdown("##### Actual Quantities")
            for ba_i, ba_item in enumerate(v["bunker_act_list"]):
                bac1, bac2, bac3 = st.columns([2, 2, 0.6])
                with bac1:
                    ba_item["qty"] = st.text_input(f"Quantity (Act) {ba_i+1}", value=ba_item.get("qty",""), key=f"ba_q_{idx}_{ba_i}")
                with bac2:
                    ba_item["type"] = st.text_input(f"Type (Act) {ba_i+1}", value=ba_item.get("type",""), key=f"ba_t_{idx}_{ba_i}")
                with bac3:
                    st.write(""); st.write("")
                    if st.button("❌", key=f"del_ba_{idx}_{ba_i}"):
                        v["bunker_act_list"].pop(ba_i); st.rerun()
            if st.button("➕ Add Actual Bunker", key=f"add_ba_{idx}"):
                v["bunker_act_list"].append({"qty": "", "type": ""}); st.rerun()

            v["bunker_boom_needed"] = st.checkbox("Bunker Boom Needed", value=v.get("bunker_boom_needed", False), key=f"bk_boom_{idx}")
            if v["bunker_boom_needed"]:
                v["bunker_boom_supplier"] = st.text_input("Bunker Boom Supplier Name", value=v.get("bunker_boom_supplier", ""), key=f"bk_bsup_{idx}")

            v["bunker_surveyor_needed"] = st.checkbox("Surveyor Needed", value=v.get("bunker_surveyor_needed", False), key=f"bk_surv_{idx}")
            if v["bunker_surveyor_needed"]:
                v["nominated_surveyor"] = st.text_input("Nominated Surveyor", value=v.get("nominated_surveyor", ""), key=f"bk_nsurv_{idx}")
            
            v["bunker_notes"] = st.text_input("Bunker Notes", value=v.get("bunker_notes", ""), key=f"bk_notes_{idx}")

        st.divider()

        # 3. Packages & Mail
        v["packages_enabled"] = st.checkbox("Packages & Mail", value=v.get("packages_enabled", False), key=f"pkg_en_{idx}")
        if v["packages_enabled"]:
            pkg_c1, pkg_c2 = st.columns(2)
            with pkg_c1:
                v["package_count"] = st.text_input("Number of Packages", value=v.get("package_count", ""), key=f"pkg_cnt_{idx}")
                v["package_deliverer"] = st.selectbox("Delivered By", ["Agent", "Runner", "Transportation"], index=0, key=f"pkg_del_{idx}")
            with pkg_c2:
                v["package_location"] = st.selectbox("Current Location", ["Not Received", "In Office", "With Transport/Runner", "On Vessel"], index=0, key=f"pkg_loc_{idx}")
            v["package_notes"] = st.text_input("Package Notes", value=v.get("package_notes", ""), key=f"pkg_notes_{idx}")

        st.divider()

        # 4. CTM
        v["ctm_enabled"] = st.checkbox("CTM (Cash to Master)", value=v.get("ctm_enabled", False), key=f"ctm_en_{idx}")
        if v["ctm_enabled"]:
            ctm_c1, ctm_c2 = st.columns(2)
            with ctm_c1:
                v["ctm_amount"] = st.text_input("Dollar Amount ($)", value=v.get("ctm_amount", ""), key=f"ctm_amt_{idx}")
                v["ctm_deliverer"] = st.text_input("Who is Delivering It?", value=v.get("ctm_deliverer", ""), key=f"ctm_del_{idx}")
            with ctm_c2:
                v["ctm_funds_received"] = st.checkbox("Funds Have Been Received", value=v.get("ctm_funds_received", False), key=f"ctm_f_rec_{idx}")
                v["ctm_funds_sent"] = st.checkbox("Funds Sent to Delivery Company", value=v.get("ctm_funds_sent", False), key=f"ctm_f_sent_{idx}")
            v["ctm_notes"] = st.text_input("CTM Notes", value=v.get("ctm_notes", ""), key=f"ctm_notes_{idx}")

        st.divider()

        # 5. Launch
        v["launch_enabled"] = st.checkbox("Launch", value=v.get("launch_enabled", False), key=f"launch_en_{idx}")
        if v["launch_enabled"]:
            launch_type_opt = st.selectbox("Launch Type", ["Stores/Provisions", "Personnel"], index=0 if v.get("launch_type", "Stores/Provisions") == "Stores/Provisions" else 1, key=f"ln_type_{idx}")
            v["launch_type"] = launch_type_opt

            ln_c1, ln_c2 = st.columns(2)
            with ln_c1:
                v["launch_company"] = st.text_input("Launch Company", value=v.get("launch_company", ""), key=f"ln_comp_{idx}")
            with ln_c2:
                v["launch_datetime"] = auto_format_datetime(st.text_input("Launch Date and Time", value=v.get("launch_datetime", ""), key=f"ln_dt_{idx}", placeholder="MM/DD/YYYY HH:MM"))
            
            if launch_type_opt == "Stores/Provisions":
                if "launch_vendors" not in v:
                    v["launch_vendors"] = [{"vendor": "", "pallets": ""}]
                st.markdown("##### Planned Vendors & Pallets")
                for lv_i, lv_item in enumerate(v["launch_vendors"]):
                    lvc1, lvc2, lvc3 = st.columns([2, 2, 0.6])
                    with lvc1:
                        lv_item["vendor"] = st.text_input(f"Planned Vendor {lv_i+1}", value=lv_item.get("vendor",""), key=f"lv_v_{idx}_{lv_i}")
                    with lvc2:
                        lv_item["pallets"] = st.text_input(f"Pallet Count {lv_i+1}", value=lv_item.get("pallets",""), key=f"lv_p_{idx}_{lv_i}")
                    with lvc3:
                        st.write(""); st.write("")
                        if st.button("❌", key=f"del_lv_{idx}_{lv_i}"):
                            v["launch_vendors"].pop(lv_i); st.rerun()
                if st.button("➕ Add Vendor & Pallets", key=f"add_lv_{idx}"):
                    v["launch_vendors"].append({"vendor": "", "pallets": ""}); st.rerun()

        st.divider()

        # 6. Vendor Deliveries
        v["vendor_del_enabled"] = st.checkbox("Vendor Deliveries", value=v.get("vendor_del_enabled", False), key=f"vd_en_{idx}")
        if v["vendor_del_enabled"]:
            if "vd_vendors" not in v:
                v["vd_vendors"] = [{"vendor": "", "pallets": "", "deliver_to_launch": False, "gate_list_received": False}]
            st.markdown("##### Vendor Deliveries Tracking")
            for vv_i, vv_item in enumerate(v["vd_vendors"]):
                vvc1, vvc2, vvc3, vvc4, vvc5 = st.columns([1.6, 1.2, 1.3, 1.3, 0.5])
                with vvc1:
                    vv_item["vendor"] = st.text_input(f"Delivery Vendor {vv_i+1}", value=vv_item.get("vendor",""), key=f"vv_v_{idx}_{vv_i}")
                with vvc2:
                    vv_item["pallets"] = st.text_input(f"Pallets {vv_i+1}", value=vv_item.get("pallets",""), key=f"vv_p_{idx}_{vv_i}")
                with vvc3:
                    st.write("")
                    dtl_clicked = st.checkbox("Deliver to Launch", value=vv_item.get("deliver_to_launch", False), key=f"dtl_{idx}_{vv_i}")
                    vv_item["deliver_to_launch"] = dtl_clicked
                    if dtl_clicked:
                        v["launch_enabled"] = True
                        if "launch_vendors" not in v:
                            v["launch_vendors"] = []
                        v_name_val = vv_item.get("vendor", "")
                        v_pals_val = vv_item.get("pallets", "")
                        existing_entry = next((lv for lv in v["launch_vendors"] if lv.get("vendor") == v_name_val), None)
                        if not existing_entry and v_name_val:
                            v["launch_vendors"].append({"vendor": v_name_val, "pallets": v_pals_val})
                with vvc4:
                    st.write("")
                    vv_item["gate_list_received"] = st.checkbox("Gate List Rec.", value=vv_item.get("gate_list_received", False), key=f"vgl_rec_item_{idx}_{vv_i}")
                with vvc5:
                    st.write("")
                    if st.button("❌", key=f"del_vv_{idx}_{vv_i}"):
                        v["vd_vendors"].pop(vv_i); st.rerun()
            if st.button("➕ Add Delivery Vendor", key=f"add_vv_{idx}"):
                v["vd_vendors"].append({"vendor": "", "pallets": "", "deliver_to_launch": False, "gate_list_received": False}); st.rerun()

        st.divider()

        # 7. Attendance Alongside
        v["attendance_enabled"] = st.checkbox("Attendance Alongside", value=v.get("attendance_enabled", False), key=f"att_en_{idx}")
        if v["attendance_enabled"]:
            if "attendees" not in v:
                v["attendees"] = [{"name": "", "company": "", "gate_list_info_rec": False}]
            st.markdown("##### Attendees Listing")
            for att_i, att_item in enumerate(v["attendees"]):
                ac1, ac2, ac3, ac4 = st.columns([1.8, 1.8, 1.2, 0.5])
                with ac1:
                    att_item["name"] = st.text_input(f"Attendee Name {att_i+1}", value=att_item.get("name",""), key=f"att_n_{idx}_{att_i}")
                with ac2:
                    att_item["company"] = st.text_input(f"Company {att_i+1}", value=att_item.get("company",""), key=f"att_c_{idx}_{att_i}")
                with ac3:
                    st.write("")
                    att_item["gate_list_info_rec"] = st.checkbox("Gate List Info Rec.", value=att_item.get("gate_list_info_rec", False), key=f"glir_{idx}_{att_i}")
                with ac4:
                    st.write("")
                    if st.button("❌", key=f"del_att_{idx}_{att_i}"):
                        v["attendees"].pop(att_i); st.rerun()
            if st.button("➕ Add Attendee", key=f"add_att_{idx}"):
                v["attendees"].append({"name": "", "company": "", "gate_list_info_rec": False}); st.rerun()

        st.divider()

        # 8. USCG COC Exam
        v["coc_required"] = st.checkbox("USCG COC Exam Required", value=v.get("coc_required", False), key=f"coc_req_{idx}")
        if v["coc_required"]:
            v["coc_performance_driven"] = st.checkbox("Performance Driven Eligible", value=v.get("coc_performance_driven", False), key=f"coc_pd_{idx}")
            if not v["coc_performance_driven"]:
                v["coc_exam_date"] = auto_format_datetime(st.text_input("Exam Date/Time", value=v.get("coc_exam_date", ""), key=f"coc_dt_{idx}", placeholder="MM/DD/YYYY HH:MM"))
                v["coc_exam_loc"] = st.text_input("Exam Location", value=v.get("coc_exam_loc", ""), key=f"coc_loc_{idx}")
            
            cw_opts = ["No", "Yes"]
            curr_cw = v.get("coc_cargo_waiver", "No")
            v["coc_cargo_waiver"] = st.selectbox("Cargo Waiver Eligible", cw_opts, index=cw_opts.index(curr_cw) if curr_cw in cw_opts else 0, key=f"coc_cw_{idx}")
            
            if v["coc_cargo_waiver"] == "Yes":
                v["coc_cargo_waiver_requested"] = st.checkbox("Cargo Waiver Requested", value=v.get("coc_cargo_waiver_requested", False), key=f"cwr_{idx}")
                v["coc_cargo_waiver_approved"] = st.checkbox("Cargo Waiver Approved", value=v.get("coc_cargo_waiver_approved", False), key=f"cwa_{idx}")

            v["coc_complete"] = st.checkbox("COC Exam Complete / Data Entered", value=v.get("coc_complete", False), key=f"coc_comp_{idx}")

        v["custom_service_notes"] = st.text_input("Custom Service / Handover Notes", value=v.get("custom_service_notes", ""), key=f"csn_{idx}")

    # SECTION 7: Compliance Checklist
    with st.expander("📋 Compliance Checklist", expanded=True):
        today_str = datetime.now().strftime("%m/%d/%Y")

        def render_check_with_date(label, key_prefix):
            c1, c2 = st.columns([1, 1])
            with c1:
                checked = st.checkbox(label, value=v.get(key_prefix, False), key=f"{key_prefix}_chk_{idx}")
                v[key_prefix] = checked
            with c2:
                if checked:
                    if not v.get(f"{key_prefix}_date"):
                        v[f"{key_prefix}_date"] = today_str
                    v[f"{key_prefix}_date"] = st.text_input("Completion Date", value=v[f"{key_prefix}_date"], key=f"{key_prefix}_dt_{idx}", placeholder="MM/DD/YYYY")
                else:
                    v[f"{key_prefix}_date"] = ""

        render_check_with_date("eNOA Filed (T-96h)", "enoa_filed")
        render_check_with_date("CBP Form 3171 Submitted", "form_3171")
        render_check_with_date("CBP TPE Called In", "tpe_called_in")
        render_check_with_date("CBP Entrance Filed", "entrance_filed")
        render_check_with_date("CBP Payment Done", "cbp_payment_done")
        render_check_with_date("CBP Clearance Filed", "clearance_filed")
        render_check_with_date("Receipt Sent to Master", "receipt_sent")
        render_check_with_date("B/L Signed & Sent", "bl_signed")
        render_check_with_date("SOF Sent to Captain", "sof_sent")
        render_check_with_date("Customer Survey Sent", "survey_sent")
        render_check_with_date("SPO Turned In", "spo_turned_in")
        render_check_with_date("CBP Complete Turned In", "cbp_complete_turned_in")
        render_check_with_date("Gate List Submitted", "gate_list_submitted")
        render_check_with_date("Berth App Submitted", "berth_app_submitted")

# ==========================================
# VIEW 2: MASTER DASHBOARD (DEFAULT)
# ==========================================
else:
    with st.sidebar:
        st.header("VesselFlow Actions")
        
        with st.expander("➕ New Vessel Form", expanded=False):
            with st.form("sidebar_vessel_form", clear_on_submit=True):
                v_name = st.text_input("Vessel Name (Required)")
                v_imo = st.text_input("IMO Number")
                v_terminal = st.text_input("Terminal")
                v_dock = st.text_input("Dock / Berth")
                v_eta_raw = st.text_input("Initial ETA", placeholder="MM/DD/YYYY HH:MM")
                v_eta = auto_format_datetime(v_eta_raw)
                
                submitted = st.form_submit_button("Save Vessel", use_container_width=True)
                if submitted:
                    if v_name:
                        new_vessel = {
                            "name": v_name,
                            "imo": v_imo if v_imo else "",
                            "flag": "", "call_sign": "", "loa": "", "deadweight": "", "beam": "",
                            "dim_unit": "Feet (ft)",
                            "role": "", "call_type": "Fairwater", "principal_fairwater": "", "principal_s5": "",
                            "owner_name": "", "charterer_name": "", "principal_name": "",
                            "voyage_number": "", "coming_from": "", "next_port": "", "inbound_draft": "", "outbound_draft": "",
                            "terminal": v_terminal if v_terminal else "",
                            "dock": v_dock if v_dock else "",
                            "eta": v_eta if v_eta else "", "ata": "",
                            "etb": "", "atb": "",
                            "etc": "", "atc": "",
                            "etd": "", "atd": "",
                            "tug_company": "None", "tug_billing": "Nominated",
                            "inbound_ordered": False, "inbound_dest": "Berth",
                            "ib_basis": "Specific Time", "inbound_pilot_time": "",
                            "following_vessel": False, "following_vessel_name": "", "following_movement_date": "",
                            "layberth_ordered_by": "Terminal", "layberth_name": "", "layberth_reason": "Pre-Stage",
                            "anchorage_name": "", "anchorage_reason": "",
                            "shifting_ordered": False, "sh_basis": "Specific Time", "shifting_pilot_time": "", "shifting_following_name": "",
                            "departure_pilot_ordered": False, "departure_order_type": "Estimate Order", "departure_pilot_datetime": "",
                            "status_override": "Auto (Default)",
                            "enoa_filed": False, "form_3171": False, "tpe_called_in": False,
                            "entrance_filed": False, "cbp_payment_done": False, "clearance_filed": False,
                            "clearance_completed_time": "", "receipt_sent": False, "bl_signed": False,
                            "sof_sent": False, "survey_sent": False, "spo_turned_in": False,
                            "cbp_complete_turned_in": False, "outbound_pilot_ordered": False,
                            "outbound_pilot_confirmed": False, "gate_list_submitted": False,
                            "berth_app_submitted": False, "coc_required": False, "coc_complete": True,
                            "crew_change_enabled": False, "bunker_enabled": False, "packages_enabled": False,
                            "ctm_enabled": False, "launch_enabled": False, "vendor_del_enabled": False,
                            "attendance_enabled": False, "coc_req": False,
                            "crew_change_notes": "", "bunker_notes": "", "package_notes": "", "ctm_notes": "", "custom_service_notes": ""
                        }
                        st.session_state.vessels.append(new_vessel)
                        st.success(f"Successfully logged **{v_name}**!")
                        st.rerun()
                    else:
                        st.error("Please enter a Vessel Name.")

        with st.expander("📋 Weekend Handover", expanded=False):
            if st.button("Generate Report", type="primary", use_container_width=True):
                st.session_state.show_handover_panel = True
            if st.session_state.get("show_handover_panel", False):
                handover_txt = generate_handover_text(st.session_state.vessels)
                st.text_area("Copy Handover:", value=handover_txt, height=250)

    # Dashboard Header: Centered Logo Image
    col_l1, col_l2, col_l3 = st.columns([1, 1.5, 1])
    with col_l2:
        try:
            st.image("VF.png", use_container_width=True)
        except Exception:
            st.markdown("<h1 style='text-align: center;'>VesselFlow</h1>", unsafe_allow_html=True)

    st.write("---")

    if len(st.session_state.vessels) == 0:
        st.info("No vessels logged yet. Use the sidebar **New Vessel Form** to get started!")
    else:
        buckets = ["Sending Updates", "Assigned", "Sailed - Action Needed", "Sailed - Completed"]
        icons = ["📩", "📁", "🚨", "✅"]
        
        bucket_vessels = {b: [] for b in buckets}
        for idx, v in enumerate(st.session_state.vessels):
            b_name = get_vessel_bucket(v)
            bucket_vessels[b_name].append((idx, v))

        for b_name, b_icon in zip(buckets, icons):
            v_list = bucket_vessels[b_name]
            st.subheader(f"{b_icon} {b_name} ({len(v_list)})")
            
            if not v_list:
                st.caption("No vessels in this section.")
                continue

            for idx, v in v_list:
                active_status = get_current_status(v)
                
                soft_alerts, hard_alerts = calculate_alerts(v)
                if hard_alerts:
                    alert_badge = f"🚨 {len(hard_alerts)} Alert(s) - Immediate Action Required"
                elif soft_alerts:
                    alert_badge = f"⚠️ {len(soft_alerts)} alert(s) - Upcoming Action(s) Needed"
                else:
                    alert_badge = "✅"

            # Check Sabine Pilots Daylight Restriction Criteria
                def parse_numeric(val):
                    if not val:
                        return 0.0
                    nums = "".join(c for c in str(val) if c.isdigit() or c == '.')
                    try:
                        return float(nums)
                    except ValueError:
                        return 0.0

                loa_val = parse_numeric(v.get('loa', ''))
                beam_val = parse_numeric(v.get('beam', ''))
                dwt_val = parse_numeric(v.get('deadweight', ''))
                dim_unit = v.get('dim_unit', 'Feet (ft)')

                if "Meter" in dim_unit:
                    loa_ft = loa_val * 3.28084
                    beam_ft = beam_val * 3.28084
                else:
                    loa_ft = loa_val
                    beam_ft = beam_val

                is_daylighter = (dwt_val >= 85000 or loa_ft > 875 or beam_ft > 125)
                
                daylight_badge_html = '<span style="background-color: #451a03; color: #fde047; padding: 0.15rem 0.4rem; border-radius: 0.25rem; font-size: 0.75rem; font-weight: 600; margin-left: 0.5rem; border: 1px solid #713F12;">☀️ Daylight Restricted</span>' if is_daylighter else ''

                arr_s = get_single_time_override(v.get('eta'), v.get('ata'), "ETA")
                ber_s = get_single_time_override(v.get('etb'), v.get('atb'), "ETB")
                com_s = get_single_time_override(v.get('etc'), v.get('atc'), "ETC")
                dep_s = get_single_time_override(v.get('etd'), v.get('atd'), "ETD")
                
                schedule_preview = f"{arr_s}  •  {ber_s}  •  {com_s}  •  {dep_s}"
                
                # Custom HTML Ribbon Header (Name/Status left, Schedule center, Alerts right)
                st.markdown(
                    f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; background-color: #1E293B; padding: 0.6rem 1rem; border-top-left-radius: 0.375rem; border-top-right-radius: 0.375rem; border: 1px solid #334155; border-bottom: none;">
                        <div style="font-size: 1.05rem; font-weight: 700; color: #F8FAFC;">{v['name']} {daylight_badge_html} &nbsp;&nbsp;<span style="font-size: 0.85rem; font-weight: 400; color: #94A3B8;">Status: {active_status}</span></div>
                        <div style="font-size: 0.9rem; color: #CBD5E1; text-align: center;">{schedule_preview}</div>
                        <div style="font-size: 0.9rem; font-weight: 600; color: #FACC15;">{alert_badge}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                with st.expander("Expand Vessel Card", expanded=False):
                    with st.container():
                        card_col1, card_col2, card_col3 = st.columns([2, 3.5, 1.5])
                        
                        with card_col1:
                            if st.button(f"{v['name']}", key=f"link_{idx}"):
                                st.session_state.selected_index = idx
                                st.session_state.navigation = "detail"
                                st.rerun()
                            
                            term = v.get('terminal', 'Unknown')
                            dk = v.get('dock', 'Unknown')
                            st.markdown(f"**Terminal:** {term} &nbsp;|&nbsp; **Dock:** {dk}")
                            
                            voy_num = v.get('voyage_number', '')
                            if voy_num:
                                st.markdown(f"**Voyage Number:** {voy_num}")
                                
                            st.markdown(f"**Status:** {active_status}")

                            if v.get('coc_required'):
                                if v.get('coc_performance_driven'):
                                    st.caption("📋 **COC:** Performance Driven Credit")
                                else:
                                    cw_stat = f"Waiver: {v.get('coc_cargo_waiver', 'No')}"
                                    if v.get('coc_cargo_waiver') == "Yes":
                                        if v.get('coc_cargo_waiver_approved'):
                                            cw_stat += " (Approved)"
                                        elif v.get('coc_cargo_waiver_requested'):
                                            cw_stat += " (Requested)"
                                    coc_dt = v.get('coc_exam_date', 'TBD')
                                    st.caption(f"📋 **COC:** {cw_stat} | Exam: {coc_dt}")
                            
                        with card_col2:
                            st.markdown("##### ⏱️ Port Call Schedule")
                            arr_line = get_single_time_override(v.get('eta'), v.get('ata'), "ETA")
                            ber_line = get_single_time_override(v.get('etb'), v.get('atb'), "ETB")
                            com_line = get_single_time_override(v.get('etc'), v.get('atc'), "ETC")
                            dep_line = get_single_time_override(v.get('etd'), v.get('atd'), "ETD")
                            st.markdown(
                                f"{arr_line}<br>"
                                f"{ber_line}<br>"
                                f"{com_line}<br>"
                                f"{dep_line}",
                                unsafe_allow_html=True
                            )
                            
                            st.markdown("##### ⚓ Tug & Pilot Information")
                            tug_co = v.get('tug_company', 'None')
                            tug_bill = v.get('tug_billing', 'Nominated')
                            st.caption(f"**Tug:** {tug_co} ({tug_bill})")

                            p_col1, p_col2, p_col3 = st.columns(3)
                            
                            with p_col1:
                                if v.get('inbound_ordered'):
                                    ib_dest = v.get('inbound_dest', 'Berth')
                                    if v.get('following_vessel'):
                                        ib_str = f"Ordered - Following ({v.get('following_vessel_name', 'Vessel')}) to ({ib_dest})"
                                    else:
                                        ib_str = f"Ordered ({ib_dest})"
                                    st.caption(f"**Inbound:** {ib_str}")
                                else:
                                    st.caption("**Inbound:** Not Ordered")
                                    
                            with p_col2:
                                show_shifting = v.get('inbound_ordered', False) and v.get('inbound_dest', '') in ["Layberth", "Inshore Anchorage"] and v.get('shifting_ordered', False)
                                if show_shifting:
                                    sh_dest = v.get('shifting_dest', 'Berth')
                                    if v.get('sh_basis') == "Following Vessel":
                                        sh_str = f"Ordered - Following ({v.get('shifting_following_name', 'Vessel')}) to ({sh_dest})"
                                    else:
                                        sh_str = f"Ordered ({sh_dest})"
                                    st.caption(f"**Shifting:** {sh_str}")
                                else:
                                    st.caption("**Shifting:** N/A")
                                    
                            with p_col3:
                                if v.get('departure_pilot_ordered'):
                                    dep_t = v.get('departure_order_type', 'Estimate Order')
                                    st.caption(f"**Outbound:** Ordered ({dep_t})")
                                else:
                                    st.caption("**Outbound:** Not Ordered")
                            
                        with card_col3:
                            if hard_alerts:
                                st.error(f"🚨 {len(hard_alerts)} Immediate Action Required")
                            elif soft_alerts:
                                st.warning(f"⚠️ {len(soft_alerts)} Upcoming Action(s)")
                            else:
                                st.success("✅ Gate Cleared")
                                
                    if hard_alerts or soft_alerts:
                        st.markdown("---")
                        st.markdown("##### 🚨 Active Compliance & Operational Alerts")
                        for h in hard_alerts:
                            st.markdown(f'<div class="hard-alert">HARD ALERT: {h}</div>', unsafe_allow_html=True)
                        for s in soft_alerts:
                            st.markdown(f'<div class="soft-alert">SOFT ALERT: {s}</div>', unsafe_allow_html=True)
                            
                    st.divider()