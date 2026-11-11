"""Synthetic project correspondence for Riverside Apartments (Aug–Nov 2026).

Each message carries a ground-truth label used by the Notice agent eval:
  label   — change | delay | instruction | disruption | noise
  clauses — clause refs a correct notice could rely on (any one counts as a correct link)
  alt     — other categories a reasonable QS could also accept (lenient scoring)
  trigger — date the contractor became aware (where it differs from the message date)

Channels: email | wa_site (internal site WhatsApp group) | wa_design (design team WhatsApp) | diary
All people and companies are fictitious.
"""

P = {
    "walsh": ("Ciarán Walsh", "c.walsh@brennock.example"),
    "daly": ("Aoife Daly", "a.daly@brennock.example"),
    "murphy": ("Declan Murphy", "d.murphy@brennock.example"),
    "oleary": ("Tadhg O'Leary", "t.oleary@brennock.example"),
    "coughlan": ("Paddy Coughlan", "p.coughlan@brennock.example"),
    "hegarty": ("Fionnuala Hegarty", "hegarty@hkp.example"),
    "kiely": ("Mark Kiely", "m.kiely@hkp.example"),
    "fennessy": ("Niamh Fennessy", "niamh@fennessymoran.example"),
    "nagle": ("Rory Nagle", "r.nagle@kilcrea.example"),
    "roche": ("Sinéad Roche", "s.roche@voltaire-bs.example"),
    "ahern": ("Brendan Ahern", "b.ahern@lvhp.example"),
    "barry": ("Mick Barry", "mick@keelvane.example"),
    "lynch": ("Gerry Lynch", "g.lynch@torcmore.example"),
    "cashman": ("Owen Cashman", "owen@brightwater-me.example"),
    "petrauskas": ("Jurgis Petrauskas", "jurgis@laneway.example"),
    "twomey": ("Seán Twomey", "sean@slatefield.example"),
}


def m(key, channel, dt, frm, body, label="noise", clauses=(), to=(), cc=(), subject=None, alt=(), trigger=None, note=None):
    return dict(key=key, channel=channel, dt=dt, frm=frm, to=list(to), cc=list(cc), subject=subject, body=body.strip(),
                label=label, clauses=list(clauses), alt=list(alt), trigger=trigger, note=note)


MESSAGES = [
    # ---------------- August ----------------
    m("M01", "email", "2026-08-17 08:52", "daly", to=["murphy"], subject="Valuation 2 - cut-off",
      body="""Declan,

Valuation 2 cut-off is Friday 21st. Can you send me the % complete for the substructure packages and the
delivery dockets for rebar by Thursday so I can get it to Fionnuala before the 25th.

Thanks,
Aoife"""),
    m("M02", "email", "2026-08-18 10:14", "nagle", to=["murphy"], cc=["hegarty"],
      subject="Riverside - Block B foundations - RA-STR-110 rev C",
      body="""Declan,

Please find attached revision C of RA-STR-110 (Block B foundation layout). Minor update following our
review of the column loads from the revised roof plant - pad foundations P7 to P14 now 2.4m x 2.4m x 900 deep
(previously 1.8m x 1.8m x 750) and reinforcement increased to B20 at 150 both ways.

No cost implications expected. Please work to rev C from today.

Regards,
Rory Nagle
Kilcrea Consulting Engineers""",
      label="change", clauses=["9.2", "10.1"], note="Revised drawing increases pad sizes; 'no cost implications' is the engineer's view, not a Change Order"),
    m("M03", "wa_site", "2026-08-18 16:40", "oleary", body="Rebar for B pads delivered, 14t. Stored by gate 2."),
    m("M04", "wa_site", "2026-08-20 11:05", "oleary",
      body="Lads we've hit very soft ground at B4 to B6. Black silty stuff 1.2m below formation, looks like an old river channel. Keelvane have stopped digging there, waiting on Rory",
      label="change", clauses=["4.6"], alt=["delay"], note="Unforeseen ground conditions"),
    m("M05", "wa_site", "2026-08-20 11:09", "murphy", body="Don't backfill anything. Photos and depths please, I'll ring Rory."),
    m("M06", "email", "2026-08-21 14:30", "murphy", to=["walsh", "daly"], subject="FW: B4-B6 soft spot",
      body="""Ciarán / Aoife,

FYI - Rory was out this morning. He reckons it's alluvial infill, not shown on the site investigation (nearest
borehole BH4 is 30m away). Keelvane have two 21t machines and a dumper standing at B4-B6 since yesterday
lunchtime. Rest of Block B pads carrying on.

Declan""",
      label="change", clauses=["4.6"], alt=["delay", "disruption"], trigger="2026-08-20"),
    m("M07", "email", "2026-08-24 09:12", "nagle", to=["murphy"],
      subject="B4-B6 excavation",
      body="""Declan,

Following my inspection on Friday, please excavate the soft material at B4-B6 down to firm strata (expected
approx. 2.5m below formation) and replace with C16/20 mass concrete up to formation level. Keep a record of
the actual depths and volumes for each pad.

Rory""",
      label="instruction", clauses=["3.4", "9.2"], alt=["change"], note="Engineer, not the ER, instructing extra work"),
    m("M08", "wa_site", "2026-08-24 09:40", "barry", body="Mick here - we'll need the long reach for B5, 2.5m plus is too deep for the 21t with the batter. Can have it Weds"),
    m("M09", "email", "2026-08-25 15:02", "daly", to=["hegarty", "kiely"], subject="Interim Payment Application No. 2",
      body="""Fionnuala,

Please find attached Interim Payment Application No. 2 for the period to 21 August 2026, together with the
updated programme as required by clause 8.2.

Gross valuation EUR 1,284,550.00.

Kind regards,
Aoife Daly
Quantity Surveyor, Brennock Construction"""),
    m("M10", "wa_site", "2026-08-26 07:31", "oleary", body="Morning all, toolbox talk at 7.45 in the canteen, working at heights refresher"),
    m("M11", "wa_site", "2026-08-27 12:18", "lynch",
      body="Gerry from Torcmore. Still no connection details for the steel at the core walls of Block A. We were promised them on the 7th. Fab is stopped on the A cores, we can't hit the 21 Sept delivery without them",
      label="delay", clauses=["8.3"], note="Late information (8.6(b))"),
    m("M12", "email", "2026-08-28 10:45", "kiely", to=["murphy"], subject="Site meeting no. 4 - minutes",
      body="""Declan,

Minutes of site meeting no. 4 attached. Next meeting Tuesday 8 September at 10am in the site office.

Mark Kiely
Hegarty Kiely Partnership"""),
    m("M13", "wa_design", "2026-08-31 16:20", "fennessy",
      body="Hi Declan, Brendan (LVHP) wants the bin store moved to the north side beside the ESB substation, I've told him that's fine. Can you set it out there instead when you get to it?",
      label="instruction", clauses=["3.4", "9.2"], alt=["change"], note="Architect directing a relocation via WhatsApp"),
    m("M14", "wa_site", "2026-09-01 08:02", "oleary", body="Concrete pour B pads 7-10 at 10am, 32m3, pump booked"),

    # ---------------- September ----------------
    m("M15", "email", "2026-09-02 11:25", "murphy", to=["kiely"], subject="RFI 014 - Block A core wall embeds",
      body="""Mark,

RFI 014 attached - we still require the cast-in embed plate and connection details for the Block A core walls
(RA-STR-205). These were due under the Information Release Schedule on 7 August. Torcmore's fabrication is
now on hold and the steel delivery for Block A will slip if we don't have them this week.

Declan""",
      label="delay", clauses=["8.3"], trigger="2026-08-27", note="Confirms late information causing delay"),
    m("M16", "wa_site", "2026-09-03 13:15", "coughlan", body="Setting out for block A ground beams done, grid checked with Rory's lad. All good"),
    m("M17", "email", "2026-09-04 09:30", "cashman", to=["daly"], subject="Brightwater - Application 1",
      body="""Hi Aoife,

Our application no. 1 for first fix sleeves and drainage is attached. Can you confirm you have our RCT
details and the updated insurance cert from July.

Owen"""),
    m("M18", "wa_site", "2026-09-07 07:50", "oleary", body="Storm warning for Wednesday, yellow wind. Crane will be off if gusts over 45"),
    m("M19", "wa_site", "2026-09-09 15:44", "oleary", body="Crane stood down 2pm wind. Back tomorrow"),
    m("M20", "email", "2026-09-08 16:10", "kiely", to=["murphy"], cc=["hegarty"], subject="Meeting 5 actions",
      body="""Declan,

Actions from today's meeting:
- Contractor to issue 3-week lookahead by Friday.
- ER to chase engineer on RFI 014.
- Fionnuala confirmed verbally at the meeting that the Block B lift pit is to be deepened by 300mm to suit the
  revised lift supplier's requirements - Kilcrea to issue sketch.

Mark""",
      label="instruction", clauses=["3.3", "9.2"], alt=["change"], note="Oral instruction by ER recorded only in minutes"),
    m("M21", "wa_design", "2026-09-10 10:02", "roche",
      body="Declan - heads up that the sprinkler tank room in Block A basement has to go up from 4.5m x 6m to 6m x 7m after the fire engineer's review. New layout coming next week",
      label="change", clauses=["9.2"], note="Design change from M&E consultant"),
    m("M22", "email", "2026-09-11 12:00", "daly", to=["walsh"], subject="Cashflow forecast Sept",
      body="""Ciarán,

Updated cashflow attached. We're about EUR 180k behind forecast because valuation 2 was certified short on
preliminaries. I'll take it up with Fionnuala.

Aoife"""),
    m("M23", "wa_site", "2026-09-14 08:12", "lynch",
      body="Got the core wall details Friday evening finally. Fab restarting today but we've lost 3 weeks, delivery now 12 October not 21 Sept",
      label="delay", clauses=["8.3"], trigger="2026-09-14"),
    m("M24", "wa_site", "2026-09-14 08:20", "murphy", body="Thanks Gerry. Can you send that in an email with the revised fab programme"),
    m("M25", "email", "2026-09-15 09:00", "hegarty", to=["walsh"], subject="Interim Certificate No. 2",
      body="""Ciarán,

Interim Certificate No. 2 attached in the amount of EUR 1,192,300.00 (gross), less retention.

Regards,
Fionnuala"""),
    m("M26", "email", "2026-09-16 14:22", "fennessy", to=["murphy"], cc=["kiely"],
      subject="RA-ARC-200 series - rev P3",
      body="""Declan,

Updated GA plans RA-ARC-201 to 206 at rev P3 attached. Changes are coordination items only - mainly door
numbering and the revised window schedule. Window W07 type now triple glazed for acoustic reasons on the
road elevation (Block A, east side, 22 no.).

Niamh""",
      label="change", clauses=["9.2"], note="'Coordination items only' hides a specification upgrade (triple glazing)"),
    m("M27", "wa_site", "2026-09-17 17:30", "oleary", body="Block B ground floor slab poured. 96m3. Power floated"),
    m("M28", "wa_site", "2026-09-21 09:05", "barry",
      body="Mick. Irish Water crew have the road closed outside gate 1 since 8 this morning for their mains job, our muck away lorries can't get in or out. Told it's for the week",
      label="disruption", clauses=["8.5"], alt=["delay"], note="Utility works blocking access; disruption from others"),
    m("M29", "wa_site", "2026-09-21 09:30", "murphy", body="Use gate 2 for deliveries. Keep a list of lorries turned away and times."),
    m("M30", "email", "2026-09-22 10:40", "petrauskas", to=["murphy"], subject="Laneway - start date",
      body="""Declan,

Confirming our team of 6 can start drylining Block B level 1 on 12 October as per programme.

Jurgis"""),
    m("M31", "wa_site", "2026-09-23 16:00", "oleary", body="Toilets serviced. Skip swap tomorrow am."),
    m("M32", "email", "2026-09-24 11:18", "daly", to=["hegarty", "kiely"], subject="Interim Payment Application No. 3",
      body="""Fionnuala,

Application No. 3 to 21 September attached with updated programme. Gross valuation EUR 2,046,880.00.

Aoife"""),
    m("M33", "wa_design", "2026-09-25 09:15", "hegarty",
      body="Declan, following our walk round this morning - please hold off on the Block B level 1 blockwork on gridlines 3-5 until the revised layout for the accessible units comes through. Probably two weeks.",
      label="instruction", clauses=["3.3"], alt=["delay", "disruption"], note="Oral/WhatsApp instruction from ER to hold work"),
    m("M34", "wa_site", "2026-09-28 07:45", "oleary", body="Scaffold inspection done Block A, tag updated"),
    m("M35", "email", "2026-09-29 15:30", "cashman", to=["murphy"], cc=["roche"],
      subject="Sprinkler tank room",
      body="""Declan,

We've had a look at Sinéad's sketch SK-M-021 for the enlarged tank room. The tank goes from 72m3 to 110m3 and
the pumpset changes to a duty/standby diesel set. I'd say there's EUR 40-50k in that before builder's work.
Do you want a formal price?

Owen""",
      label="change", clauses=["9.2"], note="Quantifies M21; reinforces change"),
    m("M36", "wa_site", "2026-09-30 12:10", "oleary", body="Lads, BBQ Friday for the topping out of Block B frame. Burgers on Brennock."),

    # ---------------- October ----------------
    m("M37", "email", "2026-10-01 08:55", "murphy", to=["walsh"], subject="Blockwork hold B L1",
      body="""Ciarán,

Still no revised layout for the accessible units on B L1 since Fionnuala told us to hold on the 25th. I've had
to move the block layers to Block A but they'll run out of work there by Wednesday next week. The drylining start
on 12 October for B L1 is now at risk.

Declan""",
      label="delay", clauses=["8.3"], alt=["disruption"], trigger="2026-09-25"),
    m("M38", "wa_site", "2026-10-02 10:30", "coughlan", body="Level survey B L1 slab complete, max deviation 6mm. Sending report"),
    m("M39", "email", "2026-10-05 09:20", "walsh", to=["daly", "murphy"], subject="Monthly commercial review",
      body="""All,

Monthly commercial review Thursday at 2pm, Cork office. Please bring the change register and the cost to complete.

Ciarán"""),
    m("M40", "wa_site", "2026-10-06 14:50", "oleary",
      body="ESB networks crew turned up today to pull the new supply cable and took over the whole north access road with their trucks. Our concrete pour for the bin store base had to be cancelled, pump sent away. Lost the afternoon for 5 men",
      label="disruption", clauses=["8.5"], note="Utility (engaged by Employer) disrupting works"),
    m("M41", "email", "2026-10-07 13:05", "kiely", to=["murphy"], subject="Accessible units - B L1 revised layout",
      body="""Declan,

Revised layout for the accessible units at Block B level 1 attached (RA-ARC-212 rev P1). Partitions on gridlines
3-5 move 600mm to enlarge the bathrooms; 4 no. doors change to 1000mm clear opening. You can now proceed.

Mark""",
      label="change", clauses=["9.2"], note="Revised drawing = Change, no Change Order"),
    m("M42", "wa_site", "2026-10-08 16:20", "petrauskas", body="Jurgis - so are we starting B L1 on the 12th or not? I need to know to plan the lads"),
    m("M43", "wa_site", "2026-10-08 16:41", "murphy", body="Not B L1, the blockwork's behind because of the layout change. Start A L2 on the 12th, B L1 from the 26th earliest"),
    m("M44", "email", "2026-10-09 11:00", "nagle", to=["murphy"], cc=["hegarty"], subject="Lift pit Block B - SK-S-031",
      body="""Declan,

Sketch SK-S-031 attached for the deepened lift pit in Block B (as agreed at meeting 5). Pit base now 1,850 below
FFL with a 300mm thicker base slab and waterproof concrete with crystalline admixture. Note the pit is already
cast, so the existing base will need to be broken out.

Rory""",
      label="change", clauses=["9.2"], note="Formal sketch for the change; breaking out cast work"),
    m("M45", "wa_site", "2026-10-12 08:05", "oleary", body="Delivery of steel for Block A today 10am, 3 loads. Crane booked all day."),
    m("M46", "email", "2026-10-13 09:35", "cashman", to=["murphy"], subject="Access to Block A plant room",
      body="""Declan,

Our lads couldn't get into the Block A plant room again this morning - the Employer's own furniture/kitchen
contractor (Corran Fit-Out) have it full of their crates since last Thursday and they won't move them without
instruction from LVHP. That's 4 men half idle on Thursday, Friday and today.

Owen""",
      label="disruption", clauses=["8.5"], trigger="2026-10-08", note="Employer's other contractor obstructing"),
    m("M47", "wa_site", "2026-10-14 07:30", "oleary", body="Heavy rain forecast all week. Pumps checked."),
    m("M48", "email", "2026-10-15 16:15", "fennessy", to=["murphy"], subject="Re: Brick sample panel",
      body="""Declan,

Thanks for building the sample panel. Brendan and I looked at it this afternoon. We'd like to go with the
darker Cumbrian brick instead of the specified red multi - can you get that ordered for all elevations? I'll
update the spec.

Niamh""",
      label="instruction", clauses=["3.4", "9.2"], alt=["change"], note="Architect directing a material change"),
    m("M49", "wa_site", "2026-10-16 12:00", "oleary", body="Fire alarm test 12 noon, don't panic"),
    m("M50", "email", "2026-10-19 10:50", "daly", to=["walsh"], subject="Change register",
      body="""Ciarán,

Change register updated. 7 open items. I'll need Declan's records for the B4-B6 dig out to price that one.

Aoife"""),
    m("M51", "wa_site", "2026-10-20 15:20", "oleary",
      body="Lift pit B broken out. 2 days with breaker and 3 lads, plus skip. Pouring new base Thursday",
      label="noise", note="Progress update on an already-flagged change (M44); records only"),
    m("M52", "email", "2026-10-21 14:45", "twomey", to=["murphy"], subject="Roof start Block A",
      body="""Declan,

Confirming we'll be on Block A roof from 2 November. Scaffold to be handed over with edge protection.

Seán"""),
    m("M53", "email", "2026-10-22 09:10", "kiely", to=["murphy"], cc=["hegarty"], subject="Drainage - revised outfall",
      body="""Declan,

Irish Water have rejected the connection at manhole MH12. The outfall will now need to go to the existing
manhole on the Ballincollig Road (MH-IW-07), approx. 85m further, including a road crossing. Kilcrea will issue
the revised drainage layout next week. Please hold the external drainage on the south side until then.

Mark""",
      label="change", clauses=["9.2"], alt=["delay", "instruction"]),
    m("M54", "email", "2026-10-23 11:30", "daly", to=["hegarty", "kiely"], subject="Interim Payment Application No. 4",
      body="""Fionnuala,

Application No. 4 to 21 October attached with updated programme. Gross valuation EUR 3,104,220.00.

Aoife"""),
    m("M55", "wa_site", "2026-10-27 08:15", "oleary", body="Back after the bank holiday. Hoarding damaged by wind on the road side, fixing it this morning"),
    m("M56", "wa_site", "2026-10-28 13:40", "coughlan",
      body="Checking the B L2 setting out against the new P3 plans and the window openings on the east elevation don't match the structural drawings - RA-ARC-204 shows 1800 wide, RA-STR-230 has the lintels at 1500. Which one is right?",
      label="change", clauses=["5.4"], alt=["instruction"], note="Discrepancy between documents"),
    m("M57", "email", "2026-10-29 16:00", "lynch", to=["murphy"], subject="Torcmore - Block B steel",
      body="""Declan,

Heads up - our galvaniser in Mallow has had a fire and is closed for at least three weeks. Block B steel was due
to go for galvanising on 2 November. We're trying another galvaniser but expect at least a two week delay to the
Block B steel delivery.

Gerry""",
      label="noise", alt=["delay"], note="Subcontractor's own supply problem: contractor risk, not a Delay Event under 8.6"),
    m("M58", "wa_site", "2026-11-02 07:55", "oleary", body="Slatefield on the roof today. Scaffold handed over yesterday."),
    m("M59", "email", "2026-11-03 10:25", "hegarty", to=["walsh"], subject="Extension of time - Block A steel",
      body="""Ciarán,

I note from the updated programme with Application No. 4 that you are showing a 3 week delay to the Block A
frame. I have no record of a notice under clause 8.3 for this. Please clarify.

Fionnuala""",
      label="delay", clauses=["8.3"], trigger="2026-09-14", note="ER flags missing delay notice"),
    m("M60", "wa_design", "2026-11-04 11:40", "hegarty",
      body="Declan, as discussed on site - go ahead with the extra 4 no. external lighting columns along the north path, Niamh will send the spec. LVHP have agreed.",
      label="instruction", clauses=["3.3", "9.2"], alt=["change"], note="ER oral instruction confirmed on WhatsApp only"),
    m("M61", "wa_site", "2026-11-05 15:10", "barry",
      body="Started the south drainage again where we were told to hold? Asking because we've had the crew sat since the 23rd waiting on the new outfall drawing and nothing's come",
      label="disruption", clauses=["8.5"], alt=["delay"], trigger="2026-10-23"),
    m("M62", "email", "2026-11-06 09:00", "walsh", to=["daly", "murphy"], subject="Christmas shutdown",
      body="""All,

Site will close from Monday 21 December and reopen Monday 4 January. Please plan deliveries and subcontractor
programmes accordingly.

Ciarán"""),
]

DIARY = [
    ("2026-08-20", "murphy", """Weather: dry, 17C. Labour: Brennock 9, Keelvane 6, Torcmore 0.
Block B pad excavation continuing. At 11:00 soft dark silt encountered at B4-B6 approx 1.2m below formation.
Excavation at B4-B6 stopped. Engineer contacted. Photos taken (IMG_2210-2224). 2 x 21t excavators and 1 x 6t
dumper standing from 11:30.""",
     dict(label="change", clauses=["4.6"], alt=["delay", "disruption"])),
    ("2026-08-21", "murphy", """Weather: showers. Labour: Brennock 9, Keelvane 6.
R. Nagle (Kilcrea) on site 09:00 to inspect B4-B6. Keelvane plant at B4-B6 standing all day. Pads P7-P10
excavated and blinded.""",
     dict(label="noise", alt=["change", "disruption"], note="Continuation of M04 event")),
    ("2026-08-26", "murphy", """Weather: dry. Labour: Brennock 10, Keelvane 7.
Long reach excavator on site. B5 excavated to 2.6m below formation, B4 2.4m, B6 2.5m. Mass concrete 41m3
poured in B4-B6. Depths recorded on marked-up RA-STR-110.""",
     dict(label="noise", note="Records for the ground conditions event")),
    ("2026-09-01", "murphy", """Weather: dry, warm. Labour: Brennock 11, Keelvane 6.
Pour B pads P7-P10 32m3. Cubes taken. No issues.""", dict(label="noise")),
    ("2026-09-09", "murphy", """Weather: wind gusts to 60km/h from 13:00. Labour: Brennock 12, Torcmore 0.
Tower crane stood down 14:00-17:00 due to wind. Blockwork Block A L0 continued.""",
     dict(label="noise", alt=["delay"], note="Normal weather, not exceptional (8.6(e) is 1 in 10 year)")),
    ("2026-09-17", "murphy", """Weather: dry. Labour: Brennock 14.
Block B ground floor slab poured 96m3. Fennessy Moran visited 11:00 - N. Fennessy asked verbally for the
balcony upstand height on Block B to be increased from 150 to 250mm for all balconies. Told her we would need it
from the ER.""",
     dict(label="instruction", clauses=["3.4", "9.2"], alt=["change"], note="Hidden oral direction from architect in diary")),
    ("2026-09-21", "murphy", """Weather: dry. Labour: Brennock 12, Keelvane 5.
Irish Water contractor closed public road outside gate 1 from 08:00. Muck away lorries diverted via gate 2,
approx 40 min delay per load. 6 loads turned away before diversion agreed.""",
     dict(label="disruption", clauses=["8.5"], alt=["delay"])),
    ("2026-09-25", "murphy", """Weather: overcast. Labour: Brennock 13, Laneway 0.
F. Hegarty and M. Kiely on site 08:30 walk round. FH instructed hold on blockwork B L1 gridlines 3-5 pending
revised accessible unit layout. Block layers moved to Block A L1.""",
     dict(label="instruction", clauses=["3.3"], alt=["delay", "disruption"])),
    ("2026-10-06", "murphy", """Weather: dry. Labour: Brennock 12.
Network operator's crew blocked north access road 10:00-16:00. Bin store base pour cancelled, pump sent away
(cancellation charge to follow). 5 operatives redeployed to clean-up.""",
     dict(label="disruption", clauses=["8.5"])),
    ("2026-10-12", "murphy", """Weather: dry. Labour: Brennock 12, Torcmore 6, Laneway 6.
Block A steel 3 loads delivered and erection started core A1. Laneway started A L2.""", dict(label="noise")),
    ("2026-10-14", "murphy", """Weather: heavy rain all day (approx 22mm). Labour: Brennock 8.
External works suspended. Internal blockwork continued.""", dict(label="noise", alt=["delay"])),
    ("2026-10-20", "murphy", """Weather: dry. Labour: Brennock 11.
Lift pit Block B existing base broken out per SK-S-031. 3 operatives + breaker 2 days. 2 skips.""",
     dict(label="noise", note="Records for lift pit change")),
    ("2026-10-23", "murphy", """Weather: dry. Labour: Brennock 10, Keelvane 4.
External drainage south side held per M. Kiely email 22/10. Keelvane crew of 4 + 13t excavator standing
from 10:00 waiting on revised drainage layout.""",
     dict(label="disruption", clauses=["8.5"], alt=["delay"])),
    ("2026-11-04", "murphy", """Weather: dry, cold. Labour: Brennock 12, Slatefield 5.
F. Hegarty on site 10:00. Confirmed verbally extra external lighting columns (4 no.) along north path.
Roofing Block A progressing.""",
     dict(label="instruction", clauses=["3.3", "9.2"], alt=["change"])),
]

# Party roles for the project record (used by the seed and the eval)
ROLES = {
    "walsh": ("contractor", "Brennock Construction Ltd"),
    "daly": ("contractor_internal", "Brennock Construction Ltd"),
    "murphy": ("contractor_internal", "Brennock Construction Ltd"),
    "oleary": ("contractor_internal", "Brennock Construction Ltd"),
    "coughlan": ("contractor_internal", "Brennock Construction Ltd"),
    "hegarty": ("employers_representative", "Hegarty Kiely Partnership"),
    "kiely": ("employers_representative", "Hegarty Kiely Partnership"),
    "fennessy": ("architect", "Fennessy Moran Architects"),
    "nagle": ("engineer", "Kilcrea Consulting Engineers"),
    "roche": ("consultant", "Voltaire Building Services"),
    "ahern": ("employer", "Lee Valley Housing Partnership CLG"),
    "barry": ("subcontractor", "Keelvane Civils Ltd"),
    "lynch": ("subcontractor", "Torcmore Steel Fabrications Ltd"),
    "cashman": ("subcontractor", "Brightwater M&E Ltd"),
    "petrauskas": ("subcontractor", "Laneway Drylining Ltd"),
    "twomey": ("subcontractor", "Slatefield Roofing Ltd"),
}
