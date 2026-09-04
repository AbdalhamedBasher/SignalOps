# Transport and backhaul faults

## Confirm the transport fault before dispatching
Applies to: BACKHAUL_DOWN, S1_LINK_FAILURE

1. Check whether the far-end router still sees the link, to separate a fibre
   break from a local interface failure.
2. Read the optical power levels at both ends. Levels at or below the receiver
   sensitivity threshold indicate a physical break rather than a configuration
   fault.
3. Confirm the alarm is not a knock-on effect of a scheduled works window
   before raising a field ticket.

## Fail traffic over to the protection path
Applies to: BACKHAUL_DOWN

1. Verify the protection path is carrying no faults of its own.
2. Trigger the protection switch and confirm traffic recovers at the far end.
3. Leave the working path administratively down until the fibre is repaired, so
   automatic reversion cannot drop traffic a second time.

## Investigate degraded microwave performance
Applies to: MW_SNR_DEGRADED, PACKET_LOSS_HIGH

1. Compare the current signal-to-noise margin against the link's design margin.
   A shortfall that tracks local weather is fading, not a hardware fault.
2. Check the adaptive modulation state. A link that has dropped to a lower
   scheme is protecting itself and will carry reduced capacity.
3. If the margin loss is persistent and not weather-correlated, inspect the
   antenna alignment and waveguide for water ingress.

## Escalate a transport fault
Applies to: BACKHAUL_DOWN, S1_LINK_FAILURE, PACKET_LOSS_HIGH

1. Escalate to the transport on-call engineer when a site has been isolated for
   more than fifteen minutes.
2. Include the affected subscriber count and the site identifier in the
   escalation, because they set the repair priority.
3. Notify the customer operations desk before, not after, the first customer
   complaint arrives.
