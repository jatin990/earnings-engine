"""Update Nepal ABC Trek itinerary: move bungee to last day, remove flood warnings, update route."""
import sys
sys.path.insert(0, "D:/earnings-engine")
from earnings_engine.data.db import get_db_connection
from datetime import datetime

conn = get_db_connection()
now_str = datetime.now().isoformat(timespec="seconds")

# 1. Clear old activities and itinerary for ABC trek
conn.execute("DELETE FROM trip_activities WHERE trip_id = ?", ("trip_nepal_abc_2026",))
conn.execute("DELETE FROM trip_itinerary_days WHERE trip_id = ?", ("trip_nepal_abc_2026",))

# 2. Seed new activities (bungee is LAST day now)
activities = [
    ("act_poon_sunrise", "trip_nepal_abc_2026", "Owner", "owner",
     "Poon Hill Sunrise Trek (4am, 3210m)", "Poon Hill, Ghorepani, Nepal",
     0.0, 0, "accepted", now_str),
    ("act_abc_summit", "trip_nepal_abc_2026", "Owner", "owner",
     "Annapurna Base Camp Summit Celebration", "ABC (4130m), Nepal",
     0.0, 0, "accepted", now_str),
    ("act_bungee_kushma", "trip_nepal_abc_2026", "Owner", "owner",
     "Kushma Bungee Jump (228m — World's Highest)", "Kushma, Parbat District, Nepal",
     18000.0, 0, "accepted", now_str),
]
for a in activities:
    conn.execute("""
        INSERT OR IGNORE INTO trip_activities
        (id, trip_id, suggested_by_name, suggested_by_role, activity_title,
         location, approx_cost, votes_count, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, a)

# 3. New 11-day itinerary — NO flood warnings, bungee on last day
days = [
    # Day 1: Arrive Pokhara
    ("itin_abc_d01", "trip_nepal_abc_2026", 1, "2026-10-01",
     "Arrive Pokhara & Acclimatise",
     "Fly into Pokhara via Kathmandu. Check into hotel, rest and acclimatise. "
     "Evening stroll along Phewa Lakeside. Gear check and trek briefing.",
     "Pokhara Airport (820m)", "Pokhara (820m)",
     820, 0.0, None, "Hotel Butterfly, Pokhara", "B/D", "Rest", None),

    # Day 2: Drive Nayapul, trek Tikhedhunga
    ("itin_abc_d02", "trip_nepal_abc_2026", 2, "2026-10-02",
     "Drive to Nayapul → Trek to Tikhedhunga",
     "Drive from Pokhara to Nayapul (~2h). Begin the ABC trail through Birethanti village. "
     "Gradual walk along the Modi Khola river valley to Tikhedhunga.",
     "Pokhara (820m)", "Tikhedhunga (1540m)",
     1540, 12.0, 5.0, "Teahouse, Tikhedhunga", "B/L/D", "Moderate", None),

    # Day 3: Tikhedhunga → Ghorepani
    ("itin_abc_d03", "trip_nepal_abc_2026", 3, "2026-10-03",
     "Tikhedhunga → Ghorepani via Ulleri",
     "Steep ascent via the famous 3,300 stone steps through Ulleri village. "
     "Trek through rhododendron and oak forest. Arrive Ghorepani with panoramic "
     "Annapurna South and Dhaulagiri views.",
     "Tikhedhunga (1540m)", "Ghorepani (2860m)",
     2860, 9.0, 6.0, "Teahouse, Ghorepani", "B/L/D", "Hard", None),

    # Day 4: Poon Hill sunrise → Tadapani
    ("itin_abc_d04", "trip_nepal_abc_2026", 4, "2026-10-04",
     "Poon Hill Sunrise (4am) → Trek to Tadapani",
     "Pre-dawn 4am hike to Poon Hill (3210m) for 360° sunrise panorama: Annapurna I, "
     "Dhaulagiri, Machhapuchhre (Fish Tail). Descend through rhododendron forest to Tadapani.",
     "Ghorepani (2860m) → Poon Hill (3210m)", "Tadapani (2630m)",
     2630, 11.0, 7.0, "Teahouse, Tadapani", "B/L/D", "Moderate", None),

    # Day 5: Tadapani → Chhomrong
    ("itin_abc_d05", "trip_nepal_abc_2026", 5, "2026-10-05",
     "Tadapani → Chhomrong",
     "Descend through dense forest to the terraced village of Chhomrong, the last major "
     "settlement before entering the Annapurna Sanctuary. Stunning views of Annapurna "
     "South and Machhapuchhre.",
     "Tadapani (2630m)", "Chhomrong (2170m)",
     2170, 8.0, 5.0, "Teahouse, Chhomrong", "B/L/D", "Moderate", None),

    # Day 6: Chhomrong → Bamboo (via upper Sinuwa bypass — standard route since 2025)
    ("itin_abc_d06", "trip_nepal_abc_2026", 6, "2026-10-06",
     "Chhomrong → Bamboo (via Sinuwa)",
     "Descend from Chhomrong stone steps to Sinuwa village, then continue into the "
     "Annapurna Sanctuary through dense bamboo and rhododendron forest. The upper trail "
     "via Sinuwa is the current standard route.",
     "Chhomrong (2170m)", "Bamboo (2310m)",
     2310, 10.0, 6.0, "Teahouse, Bamboo", "B/L/D", "Hard", None),

    # Day 7: Bamboo → Deurali
    ("itin_abc_d07", "trip_nepal_abc_2026", 7, "2026-10-07",
     "Bamboo → Deurali (via Himalaya Hotel)",
     "Trek deeper into the Modi Khola gorge. Pass through Dobhan and Himalaya Hotel. "
     "The trail narrows between towering canyon walls. Look for Himalayan tahr and "
     "waterfalls above Himalaya Hotel.",
     "Bamboo (2310m)", "Deurali (3230m)",
     3230, 8.0, 5.0, "Teahouse, Deurali", "B/L/D", "Hard", None),

    # Day 8: Deurali → ABC
    ("itin_abc_d08", "trip_nepal_abc_2026", 8, "2026-10-08",
     "Deurali → Annapurna Base Camp",
     "Final ascent into the Annapurna Sanctuary. Pass Machhapuchhre Base Camp (MBC, 3700m) "
     "with Fish Tail peak towering overhead. Arrive at ABC (4130m) — surrounded by "
     "Annapurna I (8091m), Annapurna South, Gangapurna, and Machhapuchhre. Golden hour photography.",
     "Deurali (3230m)", "Annapurna Base Camp (4130m)",
     4130, 8.0, 5.0, "ABC Camp teahouse (4130m)", "B/L/D", "Hard", None),

    # Day 9: ABC → Bamboo (descent)
    ("itin_abc_d09", "trip_nepal_abc_2026", 9, "2026-10-09",
     "ABC → Bamboo (Descent)",
     "Descend from the sanctuary back through MBC, Deurali, Himalaya Hotel, Dobhan to Bamboo. "
     "Faster going down — the altitude drop is significant (4130m → 2310m) so take care on knees.",
     "Annapurna Base Camp (4130m)", "Bamboo (2310m)",
     2310, 14.0, 7.0, "Teahouse, Bamboo", "B/L/D", "Moderate", None),

    # Day 10: Bamboo → Nayapul → Pokhara
    ("itin_abc_d10", "trip_nepal_abc_2026", 10, "2026-10-10",
     "Bamboo → Nayapul → Pokhara",
     "Final trekking day. Descend through Sinuwa, Chhomrong, and back to Nayapul. "
     "Drive from Nayapul to Pokhara (~2h). Hot shower, lakeside celebration dinner!",
     "Bamboo (2310m)", "Pokhara (820m)",
     820, 22.0, 9.0, "Hotel Butterfly, Pokhara", "B/L/D", "Easy", None),

    # Day 11: Pokhara — Kushma Bungee Jump (end of trip celebration!)
    ("itin_abc_d11", "trip_nepal_abc_2026", 11, "2026-10-11",
     "Kushma Bungee Jump (228m) — World's Highest",
     "Early morning drive from Pokhara to Kushma (~3h, Parbat District). "
     "Jump from the 228m suspension bridge — the world's highest bungee jump — "
     "over the Bhote Koshi river gorge. Once-in-a-lifetime experience! "
     "Return to Pokhara by evening. Departure or extra night in Pokhara.",
     "Kushma, Parbat District (228m bungee)", "Pokhara (820m)",
     820, 180.0, None, "Hotel Butterfly, Pokhara", "B/L/D", "Easy",
     "Optional: rafting on the Trisuli River en route to Kushma."),
]
for d in days:
    conn.execute("""
        INSERT OR IGNORE INTO trip_itinerary_days
        (day_id, trip_id, day_number, date, title, description,
         start_point, end_point, altitude_meters, distance_km,
         duration_hours, accommodation, meals, difficulty, trail_alert)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, d)

# 4. Update trip notes
conn.execute("""
    UPDATE trips SET notes = ?, flight_details = ?
    WHERE id = ?
""", (
    "11-day ABC trek (4130m) + Kushma Bungee Jump (228m, world's highest) on final day. "
    "Route: Pokhara → Nayapul → Tikhedhunga → Ghorepani → Poon Hill → Tadapani → "
    "Chhomrong → Sinuwa → Bamboo → Deurali → MBC → ABC → back. "
    "Packing checklist for all group members included.",
    "IndiGo 6E-XXX | DEL → KTM → PKR | Oct 01, 2026 | Return: Oct 12, 2026",
    "trip_nepal_abc_2026",
))

conn.commit()

# Verify
trips = conn.execute("SELECT id, title, notes FROM trips WHERE id = ?", ("trip_nepal_abc_2026",)).fetchone()
days_count = conn.execute("SELECT count(*) FROM trip_itinerary_days WHERE trip_id = ?", ("trip_nepal_abc_2026",)).fetchone()[0]
activities_count = conn.execute("SELECT count(*) FROM trip_activities WHERE trip_id = ?", ("trip_nepal_abc_2026",)).fetchone()[0]
print(f"Trip: {trips[1]}")
print(f"Notes: {trips[2][:100]}...")
print(f"Itinerary days: {days_count}")
print(f"Activities: {activities_count}")
conn.close()
