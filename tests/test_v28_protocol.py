import unittest
from src.models.v26_protocol import AcquisitionSettings,validate_record


def done(rate=5):
    return dict(SAMPLES=100,TOTAL=400,HEX_CHARS=800,BLOCKS=1,ACTIVE_PRE=30,
                RATE=100000000,CFG_RATE_MSPS=rate,ACTIVE_RATE_MSPS=rate)


class V28ProtocolTests(unittest.TestCase):
    def test_active_record_rate_must_match_requested_rate(self):
        with self.assertRaises(ValueError):
            validate_record(done(5),AcquisitionSettings(len_mode=1,length=100))

    def test_bad_active_rate_is_not_silently_treated_as_100_msps(self):
        for rate in (0,101):
            with self.subTest(rate=rate),self.assertRaises(ValueError):validate_record(done(rate))

    def test_v28_time_mode_readback_uses_time_and_rate_not_samples_register(self):
        settings=AcquisitionSettings(length=2)
        status=dict(LENMODE=0,TIME=2,CFG_SAMPLES=123,PRE=30,MODE=0,VTH=2048,VCMP=0,
                    ITH=2048,ICMP=4,ENABLE=3,GAP_MS=1000,CFG_RATE_MSPS=100)
        self.assertTrue(settings.matches(status))

    def test_time_and_point_lengths_and_complete_command(self):
        settings=AcquisitionSettings(length=2,rate_msps=5)
        self.assertEqual(settings.samples,10000)
        self.assertEqual(settings.pre_samples,3000)
        self.assertEqual(settings.command(),b'CFG 0,2,30,0,2048,0,2048,4,3,1000,5\r')
        self.assertEqual(AcquisitionSettings(len_mode=1,length=10000,rate_msps=5).samples,10000)
        self.assertEqual(AcquisitionSettings(length=200,rate_msps=100).samples,20000000)

    def test_invalid_and_legacy_rate_configuration(self):
        for rate in (0,101,-1,1.5,True):
            with self.subTest(rate=rate),self.assertRaises(ValueError):AcquisitionSettings(rate_msps=rate)
        self.assertEqual(AcquisitionSettings().command(include_rate=False),b'CFG 0,10,30,0,2048,0,2048,4,3,1000\r')
        with self.assertRaises(ValueError):AcquisitionSettings(rate_msps=5).command(include_rate=False)


if __name__=='__main__':unittest.main()
