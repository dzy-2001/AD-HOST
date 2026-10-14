"""Confirmed probe chain: ADC ±1 V, amplifier attenuation 6, V probe 5000, I probe 40 A/V."""


def sma_voltage(raw):
    return (raw*(2.0/4096.0)-1.0)*6.0


def voltage_from_adc(raw):
    return sma_voltage(raw)*5000.0


def current_from_adc(raw):
    return sma_voltage(raw)*40.0


CALIBRATION = dict(adc_bits=12,adc_levels=4096,adc_min_v=-1,adc_span_v=2,
                   amplifier_attenuation=6,voltage_probe_attenuation=5000,current_probe_a_per_v=40)
