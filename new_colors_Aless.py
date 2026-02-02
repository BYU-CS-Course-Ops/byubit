from byubit import Bit


@Bit.empty_world(5,5)
def main(bit):
    bit.paint("green")


if __name__ == '__main__':
    main(Bit.new_bit)