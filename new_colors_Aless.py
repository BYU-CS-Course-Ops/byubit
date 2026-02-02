from byubit import Bit


@Bit.empty_world(5,5)
def main(bit):
    bit.paint("green")

    bit.move()
    bit.move()

    bit.paint('blue')

    bit.move()
    bit.move()

    bit.paint('red')


if __name__ == '__main__':
    main(Bit.new_bit)